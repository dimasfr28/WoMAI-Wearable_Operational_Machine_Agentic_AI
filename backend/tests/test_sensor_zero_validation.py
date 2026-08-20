"""Unit tests for _is_zero_reading — sensor readings where any raw value is
exactly 0 are treated as a faulty/disconnected sensor, not real data."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.api.routes_sensor import _is_zero_reading
from app.schemas.sensor import SensorReadingIn


def _reading(**overrides) -> SensorReadingIn:
    defaults = dict(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        air_temperature_k=300.0,
        process_temperature_k=310.0,
        rotational_speed_rpm=1500,
        tool_wear_min=10.0,
    )
    defaults.update(overrides)
    return SensorReadingIn(**defaults)


class IsZeroReadingTestCase(unittest.TestCase):
    def test_all_nonzero_values_is_not_flagged(self):
        self.assertFalse(_is_zero_reading(_reading()))

    def test_zero_air_temperature_is_flagged(self):
        self.assertTrue(_is_zero_reading(_reading(air_temperature_k=0)))

    def test_zero_process_temperature_is_flagged(self):
        self.assertTrue(_is_zero_reading(_reading(process_temperature_k=0)))

    def test_zero_rotational_speed_is_flagged(self):
        self.assertTrue(_is_zero_reading(_reading(rotational_speed_rpm=0)))

    def test_zero_tool_wear_is_flagged(self):
        self.assertTrue(_is_zero_reading(_reading(tool_wear_min=0)))


if __name__ == "__main__":
    unittest.main()
