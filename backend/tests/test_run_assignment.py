"""Unit tests for assign_run_id's timestamp+tool-wear-sync run-clustering rule."""
from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import tests.sqlite_compat  # noqa: F401

from app.api.routes_sensor import assign_run_id
from app.config import settings
from app.db.models import Base, Machine, SensorReading, SensorRun
from app.schemas.sensor import SensorReadingIn

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def _reading(tool_wear_min: float, timestamp: datetime) -> SensorReadingIn:
    return SensorReadingIn(
        timestamp=timestamp,
        air_temperature_k=300.0,
        process_temperature_k=310.0,
        rotational_speed_rpm=1500,
        tool_wear_min=tool_wear_min,
    )


class AssignRunIdTestCase(unittest.TestCase):
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
        self.t0 = datetime(2026, 1, 1, 8, 0, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.db.close()
        with test_engine.connect() as conn:
            with conn.begin():
                for table in reversed(Base.metadata.sorted_tables):
                    conn.execute(table.delete())

    def _seed_first_reading(self, tool_wear_min: float, timestamp: datetime) -> SensorRun:
        run = assign_run_id(_reading(tool_wear_min, timestamp), self.db, str(self.machine.id))
        reading = SensorReading(
            run_id=run.id,
            reading_timestamp=timestamp,
            air_temperature_k=300.0,
            process_temperature_k=310.0,
            rotational_speed_rpm=1500,
            tool_wear_min=tool_wear_min,
            machine_failure=False,
        )
        self.db.add(reading)
        self.db.commit()
        return run

    def test_wear_increase_in_sync_with_elapsed_time_stays_same_run(self):
        first_run = self._seed_first_reading(20.0, self.t0)
        second = assign_run_id(
            _reading(25.0, self.t0 + timedelta(minutes=5)), self.db, str(self.machine.id)
        )
        self.assertEqual(second.id, first_run.id)

    def test_wear_decrease_always_starts_a_new_run(self):
        first_run = self._seed_first_reading(50.0, self.t0)
        second = assign_run_id(
            _reading(10.0, self.t0 + timedelta(minutes=1)), self.db, str(self.machine.id)
        )
        self.assertNotEqual(second.id, first_run.id)

    def test_wear_non_decreasing_but_timestamp_mismatch_beyond_tolerance_starts_new_run(self):
        first_run = self._seed_first_reading(20.0, self.t0)
        # wear delta 5, timestamp delta 3 hours (180 min) -> mismatch 175min >> tolerance
        second = assign_run_id(
            _reading(25.0, self.t0 + timedelta(hours=3)), self.db, str(self.machine.id)
        )
        self.assertNotEqual(second.id, first_run.id)

    def test_mismatch_exactly_at_tolerance_boundary_stays_same_run(self):
        first_run = self._seed_first_reading(20.0, self.t0)
        boundary_minutes = 5 + settings.RUN_SYNC_TOLERANCE_MINUTES  # wear delta 5 + tolerance
        second = assign_run_id(
            _reading(25.0, self.t0 + timedelta(minutes=boundary_minutes)), self.db, str(self.machine.id)
        )
        self.assertEqual(second.id, first_run.id)


if __name__ == "__main__":
    unittest.main()
