"""Unit tests for assign_run_id's timestamp+tool-wear-sync run-clustering rule."""
from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "TEXT"


@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


# NOTE — deviation from the task-1 brief's verbatim test listing, added to make
# this file runnable at all; see task-1-report.md "Issues or concerns" for the
# full justification. The three @compiles overrides above only affect DDL
# rendering under sqlite. At the Python-value bind level, SQLAlchemy's Uuid
# type (postgresql.UUID subclasses it) still requires an actual uuid.UUID
# instance whenever the dialect lacks native UUID support (sqlite) and
# as_uuid=True (true for every UUID column in app.db.models) — it
# unconditionally calls value.hex. assign_run_id/_open_new_run filter/create
# rows using machine_id as a plain str (their pre-existing, unchanged-by-this-
# task signature), which works fine against real PostgreSQL (the native
# driver accepts string literals for UUID columns) but raises AttributeError
# under this sqlite in-memory test unless plain strings are coerced to
# uuid.UUID first. This patches postgresql.UUID's bind processor, for the
# sqlite dialect only, to accept both.
_pg_uuid_bind_processor = PG_UUID.bind_processor


def _sqlite_tolerant_uuid_bind_processor(self, dialect):
    processor = _pg_uuid_bind_processor(self, dialect)
    if processor is None or dialect.name != "sqlite":
        return processor

    def process(value):
        if isinstance(value, str):
            value = uuid.UUID(value)
        return processor(value)

    return process


PG_UUID.bind_processor = _sqlite_tolerant_uuid_bind_processor


# NOTE — second deviation, same reason as above: DateTime(timezone=True)
# columns (e.g. SensorReading.reading_timestamp) round-trip through SQLite as
# naive datetimes — SQLite has no native tz-aware datetime storage, and the
# sqlite dialect's own DATETIME type (sqlalchemy.dialects.sqlite.base.DATETIME,
# which generic DateTime is mapped to under this dialect) always parses the
# stored string to a naive datetime, ignoring `timezone=True` entirely.
# assign_run_id's new same-run rule (Step 4) subtracts `new_reading.timestamp`
# (tz-aware, built directly by the test/pydantic, never touches the DB) from
# `last_reading.reading_timestamp` (tz-aware going in, naive coming back out
# of SQLite), which raises `TypeError: can't subtract offset-naive and
# offset-aware datetimes`. Against real PostgreSQL, TIMESTAMPTZ columns
# preserve tz-awareness on retrieval, so this never happens in production.
# Every timestamp in this app and this test is UTC, so reattaching UTC tzinfo
# to a naive value read back from sqlite is safe here.
from sqlalchemy.dialects.sqlite.base import DATETIME as _SQLITE_DATETIME

_sqlite_dt_result_processor = _SQLITE_DATETIME.result_processor


def _sqlite_tz_aware_result_processor(self, dialect, coltype):
    processor = _sqlite_dt_result_processor(self, dialect, coltype)
    if not self.timezone:
        return processor

    def process(value):
        value = processor(value) if processor else value
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    return process


_SQLITE_DATETIME.result_processor = _sqlite_tz_aware_result_processor


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
