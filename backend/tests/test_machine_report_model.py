"""Schema-level tests for MachineReport.run_id — one report row per run,
enforced by a unique constraint, while historical rows with run_id=NULL
(pre-dating this column) remain unconstrained against each other (NULL is
never considered equal to NULL for uniqueness purposes, in both SQLite and
PostgreSQL)."""
from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import tests.sqlite_compat  # noqa: F401 — SQLite DDL/UUID/datetime compat shims, see that module

from app.db.models import Base, Machine, MachineReport, Prediction, SensorReading, SensorRun

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


class MachineReportRunIdTestCase(unittest.TestCase):
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

        self.run = SensorRun(
            id=uuid.uuid4(),
            machine_id=self.machine.id,
            run_label="Run 1",
            start_timestamp=datetime.now(timezone.utc),
            end_timestamp=datetime.now(timezone.utc),
        )
        self.db.add(self.run)
        self.db.commit()

        reading = SensorReading(
            run_id=self.run.id,
            reading_timestamp=datetime.now(timezone.utc),
            air_temperature_k=300.0,
            process_temperature_k=310.0,
            rotational_speed_rpm=1500,
            tool_wear_min=10.0,
        )
        self.db.add(reading)
        self.db.commit()

        self.prediction = Prediction(
            sensor_reading_id=reading.id,
            predicted_label=False,
            failure_probability=0.1,
            model_version="test",
        )
        self.db.add(self.prediction)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        with test_engine.connect() as conn:
            with conn.begin():
                for table in reversed(Base.metadata.sorted_tables):
                    conn.execute(table.delete())

    def _report(self, run_id, report_number) -> MachineReport:
        return MachineReport(
            machine_id=self.machine.id,
            run_id=run_id,
            prediction_id=self.prediction.id,
            report_number=report_number,
            file_path=f"{report_number}.pdf",
            operating_status="Normal",
        )

    def test_two_reports_for_the_same_run_id_violate_the_unique_constraint(self):
        self.db.add(self._report(self.run.id, "RPT-1"))
        self.db.commit()
        self.db.add(self._report(self.run.id, "RPT-2"))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_two_reports_with_run_id_none_do_not_conflict(self):
        self.db.add(self._report(None, "RPT-1"))
        self.db.commit()
        self.db.add(self._report(None, "RPT-2"))
        self.db.commit()  # must not raise
        self.assertEqual(self.db.query(MachineReport).count(), 2)


if __name__ == "__main__":
    unittest.main()
