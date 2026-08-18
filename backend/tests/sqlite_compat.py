"""SQLite compatibility shims for unit tests that use an in-memory SQLite
engine as a stand-in for PostgreSQL (see e.g. test_run_assignment.py,
test_bot_api.py). Importing this module is enough to activate all five
patches below — there is nothing to call.

Why this exists as its own module: multiple test files need the exact same
five patches (three DDL-compilation overrides plus two runtime bind/result
processor fixes) to make PostgreSQL-specific column types work under SQLite.
Duplicating them by hand in every test file risks drift and makes the same
AttributeError/TypeError get independently rediscovered and fixed per file.
"""
from __future__ import annotations

import uuid
from datetime import timezone

from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.dialects.sqlite.base import DATETIME as _SQLITE_DATETIME
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "TEXT"


@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


# The three @compiles overrides above only affect DDL rendering under sqlite.
# At the Python-value bind level, SQLAlchemy's Uuid type (postgresql.UUID
# subclasses it) still requires an actual uuid.UUID instance whenever the
# dialect lacks native UUID support (sqlite) and as_uuid=True (true for every
# UUID column in app.db.models) — it unconditionally calls value.hex.
# Application code (e.g. assign_run_id/_open_new_run in routes_sensor.py)
# filters/creates rows using machine_id (and similar ids) as a plain str,
# which works fine against real PostgreSQL (the native driver accepts string
# literals for UUID columns) but raises AttributeError under an in-memory
# sqlite test unless plain strings are coerced to uuid.UUID first. This
# patches postgresql.UUID's bind processor, for the sqlite dialect only, to
# accept both.
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


# DateTime(timezone=True) columns (e.g. SensorReading.reading_timestamp)
# round-trip through SQLite as naive datetimes — SQLite has no native
# tz-aware datetime storage, and the sqlite dialect's own DATETIME type
# (sqlalchemy.dialects.sqlite.base.DATETIME, which generic DateTime is mapped
# to under this dialect) always parses the stored string to a naive datetime,
# ignoring `timezone=True` entirely. Application code that subtracts a
# tz-aware datetime (e.g. a freshly-built request timestamp, never touching
# the DB) from a tz-aware-going-in-but-naive-coming-back-out column value
# raises `TypeError: can't subtract offset-naive and offset-aware datetimes`.
# Against real PostgreSQL, TIMESTAMPTZ columns preserve tz-awareness on
# retrieval, so this never happens in production. Every timestamp in this app
# and its tests is UTC, so reattaching UTC tzinfo to a naive value read back
# from sqlite is safe here.
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
