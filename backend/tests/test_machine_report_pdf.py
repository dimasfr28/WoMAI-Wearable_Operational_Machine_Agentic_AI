"""Unit tests for _generate_machine_report_pdf's upsert-by-run behavior and
run-scoped Condition Log."""
from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import tests.sqlite_compat  # noqa: F401 — SQLite DDL/UUID/datetime compat shims, see that module

from app.api.routes_report import _generate_machine_report_pdf
from app.config import settings
from app.db.models import Base, Machine, MachineReport, Prediction, SensorReading, SensorRun
from app.schemas.report import (
    PredictionOut,
    RecommendationsOut,
    ReportOut,
    SensorSnapshotOut,
    ShapExplanationOut,
)

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def _report_out(reading: SensorReading, predicted_label: bool = False) -> ReportOut:
    return ReportOut(
        sensor=SensorSnapshotOut(
            id=str(reading.id),
            reading_timestamp=reading.reading_timestamp,
            air_temperature_k=float(reading.air_temperature_k),
            process_temperature_k=float(reading.process_temperature_k),
            rotational_speed_rpm=int(reading.rotational_speed_rpm),
            tool_wear_min=float(reading.tool_wear_min),
        ),
        prediction=PredictionOut(
            id=str(uuid.uuid4()),
            predicted_label=predicted_label,
            failure_probability=0.1,
            health_score=90.0,
            model_version="test",
            threshold=0.5,
        ),
        shap=ShapExplanationOut(base_value=0.1, features=[]),
        recommendations=RecommendationsOut(nearest_failure={}, nearest_no_failure={}, worst_case_delta={}),
        final_report_text="test report",
        llm_model="test",
        created_at=datetime.now(timezone.utc),
    )


class GenerateMachineReportPdfTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=test_engine)

    def setUp(self):
        self.db = TestingSessionLocal()
        self.machine = Machine(
            id=uuid.uuid4(), name="Test Machine", machine_type="Haas", status="running"
        )
        self.db.add(self.machine)
        self.db.commit()
        self.db.refresh(self.machine)

        self.run_a = SensorRun(
            id=uuid.uuid4(),
            machine_id=self.machine.id,
            run_label="Run 1",
            start_timestamp=datetime.now(timezone.utc),
            end_timestamp=datetime.now(timezone.utc),
        )
        self.run_b = SensorRun(
            id=uuid.uuid4(),
            machine_id=self.machine.id,
            run_label="Run 2",
            start_timestamp=datetime.now(timezone.utc),
            end_timestamp=datetime.now(timezone.utc),
        )
        self.db.add_all([self.run_a, self.run_b])
        self.db.commit()

        base_t = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
        self.reading_a1 = self._make_reading(self.run_a.id, base_t, 20.0)
        self.reading_a2 = self._make_reading(self.run_a.id, base_t + timedelta(minutes=5), 25.0)
        self.reading_b1 = self._make_reading(self.run_b.id, base_t + timedelta(hours=3), 5.0)

        self.patcher_narrative = patch(
            "app.api.routes_report.generate_machine_report_narrative",
            return_value={"condition_summary": "", "ai_diagnosis": "", "summary": ""},
        )
        self.patcher_render = patch("app.api.routes_report.render_machine_report_pdf")
        self.mock_narrative = self.patcher_narrative.start()
        self.mock_render = self.patcher_render.start()

        # report_folder.report_path()/day_dir() create real directories under
        # settings.REPORTS_DIR even though render_machine_report_pdf is
        # mocked above — point REPORTS_DIR at a throwaway temp dir instead of
        # letting it touch the real default (/data/reports).
        self.tmpdir = TemporaryDirectory()
        self.patcher_reports_dir = patch.object(settings, "REPORTS_DIR", self.tmpdir.name)
        self.patcher_reports_dir.start()

    def tearDown(self):
        self.patcher_reports_dir.stop()
        self.tmpdir.cleanup()
        self.patcher_narrative.stop()
        self.patcher_render.stop()
        self.db.close()
        with test_engine.connect() as conn:
            with conn.begin():
                for table in reversed(Base.metadata.sorted_tables):
                    conn.execute(table.delete())

    def _make_reading(self, run_id, timestamp, tool_wear_min) -> SensorReading:
        reading = SensorReading(
            run_id=run_id,
            reading_timestamp=timestamp,
            air_temperature_k=300.0,
            process_temperature_k=310.0,
            rotational_speed_rpm=1500,
            tool_wear_min=tool_wear_min,
            machine_failure=False,
        )
        self.db.add(reading)
        self.db.commit()
        self.db.refresh(reading)
        return reading

    def _make_prediction(self, reading: SensorReading) -> Prediction:
        prediction = Prediction(
            sensor_reading_id=reading.id,
            predicted_label=False,
            failure_probability=0.1,
            model_version="test",
        )
        self.db.add(prediction)
        self.db.commit()
        self.db.refresh(prediction)
        return prediction

    def test_first_reading_in_run_creates_one_report_row(self):
        prediction = self._make_prediction(self.reading_a1)
        _generate_machine_report_pdf(
            self.db, str(self.machine.id), str(self.run_a.id), prediction, _report_out(self.reading_a1)
        )
        rows = self.db.query(MachineReport).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(str(rows[0].run_id), str(self.run_a.id))

    def test_second_reading_same_run_updates_existing_row_in_place(self):
        prediction1 = self._make_prediction(self.reading_a1)
        _generate_machine_report_pdf(
            self.db, str(self.machine.id), str(self.run_a.id), prediction1, _report_out(self.reading_a1)
        )
        first_row = self.db.query(MachineReport).one()
        first_report_number = first_row.report_number
        first_file_path = first_row.file_path

        prediction2 = self._make_prediction(self.reading_a2)
        _generate_machine_report_pdf(
            self.db,
            str(self.machine.id),
            str(self.run_a.id),
            prediction2,
            _report_out(self.reading_a2, predicted_label=True),
        )

        rows = self.db.query(MachineReport).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id, first_row.id)
        self.assertEqual(rows[0].report_number, first_report_number)
        self.assertEqual(rows[0].file_path, first_file_path)
        self.assertEqual(rows[0].prediction_id, prediction2.id)
        self.assertEqual(rows[0].operating_status, "Failure")

        first_call_path = self.mock_render.call_args_list[0].kwargs["output_path"]
        second_call_path = self.mock_render.call_args_list[1].kwargs["output_path"]
        self.assertEqual(first_call_path, second_call_path)

    def test_new_run_creates_a_second_report_row(self):
        prediction1 = self._make_prediction(self.reading_a1)
        _generate_machine_report_pdf(
            self.db, str(self.machine.id), str(self.run_a.id), prediction1, _report_out(self.reading_a1)
        )
        prediction2 = self._make_prediction(self.reading_b1)
        _generate_machine_report_pdf(
            self.db, str(self.machine.id), str(self.run_b.id), prediction2, _report_out(self.reading_b1)
        )
        rows = self.db.query(MachineReport).all()
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0].report_number, rows[1].report_number)

    def test_condition_log_scoped_to_this_run_only(self):
        prediction1 = self._make_prediction(self.reading_a1)
        self._make_prediction(self.reading_a2)
        self._make_prediction(self.reading_b1)

        _generate_machine_report_pdf(
            self.db, str(self.machine.id), str(self.run_a.id), prediction1, _report_out(self.reading_a1)
        )
        condition_log = self.mock_render.call_args.kwargs["condition_log"]
        self.assertEqual(len(condition_log), 2)
        wear_values = {row.tool_wear_min for row in condition_log}
        self.assertEqual(wear_values, {20.0, 25.0})


if __name__ == "__main__":
    unittest.main()
