"""Regression test for SopOut.id — SQLAlchemy hands back a native
uuid.UUID (Sop.id: Mapped[uuid.UUID], UUID(as_uuid=True)) but SopOut
declared `id: str`, which Pydantic v2 does NOT auto-coerce from a UUID
object (unlike v1). Never caught before because the `sops` table started
empty — list_sops/create_sop/update_sop (routes_sop.py) return the ORM
object directly, so GET /sops raised a 500 ResponseValidationError as soon
as a row actually existed."""
from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone

from app.schemas.sop import SopOut


class SopOutIdCoercionTestCase(unittest.TestCase):
    def test_accepts_a_native_uuid_object_for_id(self):
        out = SopOut(
            id=uuid.uuid4(),
            title="Test SOP",
            symptoms="gejala",
            body="",
            steps=[],
            reference="",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.assertIsInstance(out.id, str)

    def test_still_accepts_a_plain_string_id(self):
        sid = str(uuid.uuid4())
        out = SopOut(
            id=sid,
            title="Test SOP",
            symptoms="gejala",
            body="",
            steps=[],
            reference="",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.assertEqual(out.id, sid)


if __name__ == "__main__":
    unittest.main()
