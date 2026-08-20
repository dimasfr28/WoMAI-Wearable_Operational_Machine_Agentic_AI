"""Unit tests for report_pdf.format_wib — Machine Report timestamps are
shown in WIB (UTC+7), not UTC."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.reports.report_pdf import format_wib


class FormatWibTestCase(unittest.TestCase):
    def test_converts_utc_to_wib_seven_hours_ahead(self):
        utc_dt = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(format_wib(utc_dt, "%H:%M"), "17:00")

    def test_crosses_midnight_into_the_next_day(self):
        utc_dt = datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc)
        self.assertEqual(format_wib(utc_dt, "%d-%m-%Y %H:%M"), "02-01-2026 03:00")


if __name__ == "__main__":
    unittest.main()
