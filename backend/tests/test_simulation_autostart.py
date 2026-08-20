"""Unit tests for SimulationManager.start_all — used by the app startup
hook (main.py) so a freshly (re)started backend process resumes producing
demo data on its own, without needing a real reading to arrive first and
re-trigger it via submit_reading()."""
from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import tests.sqlite_compat  # noqa: F401

from app.api.routes_sensor import SimulationManager
from app.db.models import Base, Machine

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


class StartAllTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=test_engine)

    def setUp(self):
        self.db = TestingSessionLocal()

    def tearDown(self):
        self.db.close()
        with test_engine.connect() as conn:
            with conn.begin():
                for table in reversed(Base.metadata.sorted_tables):
                    conn.execute(table.delete())

    def test_starts_simulation_for_every_machine_in_the_db(self):
        m1 = Machine(id=uuid.uuid4(), name="Machine 1", machine_type="Haas", status="running")
        m2 = Machine(id=uuid.uuid4(), name="Machine 2", machine_type="Haas", status="running")
        self.db.add_all([m1, m2])
        self.db.commit()

        with patch.object(SimulationManager, "start_simulation") as mock_start:
            count = SimulationManager.start_all(self.db)

        self.assertEqual(count, 2)
        called_ids = {call.args[0] for call in mock_start.call_args_list}
        self.assertEqual(called_ids, {str(m1.id), str(m2.id)})

    def test_no_machines_starts_nothing(self):
        with patch.object(SimulationManager, "start_simulation") as mock_start:
            count = SimulationManager.start_all(self.db)

        self.assertEqual(count, 0)
        mock_start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
