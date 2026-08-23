"""Unit tests for _require_iot_mode / _require_mock_mode — the synchronous
settings.MODE gate that replaced the old background-thread SimulationManager
(see app/config.py's MODE). MODE=iot: POST /sensor/readings and
/sensor/readings/batch accept real submissions, POST /sensor/mock/generate
is unavailable. MODE=mock: the reverse, so mock and real data never mix."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.api.routes_sensor import _require_iot_mode, _require_mock_mode
from app.config import settings


class RequireIotModeTestCase(unittest.TestCase):
    def test_passes_when_mode_is_iot(self):
        with patch.object(settings, "MODE", "iot"):
            _require_iot_mode()  # must not raise

    def test_rejects_when_mode_is_mock(self):
        with patch.object(settings, "MODE", "mock"):
            with self.assertRaises(HTTPException) as ctx:
                _require_iot_mode()
        self.assertEqual(ctx.exception.status_code, 403)


class RequireMockModeTestCase(unittest.TestCase):
    def test_passes_when_mode_is_mock(self):
        with patch.object(settings, "MODE", "mock"):
            _require_mock_mode()  # must not raise

    def test_rejects_when_mode_is_iot(self):
        with patch.object(settings, "MODE", "iot"):
            with self.assertRaises(HTTPException) as ctx:
                _require_mock_mode()
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
