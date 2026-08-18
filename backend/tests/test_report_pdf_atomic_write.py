"""Unit tests for report_pdf._atomic_write_pdf's temp-file-then-replace
atomicity — needed once a run's Machine Report PDF can be regenerated in
place multiple times (see _generate_machine_report_pdf's upsert-by-run
behavior, routes_report.py)."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.reports.report_pdf import _atomic_write_pdf


class AtomicWritePdfTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.output_path = Path(self.tmpdir.name) / "sub" / "report.pdf"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_writes_a_valid_pdf_and_creates_parent_dirs(self):
        _atomic_write_pdf("<html><body>Version A</body></html>", self.output_path)
        self.assertTrue(self.output_path.is_file())
        self.assertTrue(self.output_path.read_bytes().startswith(b"%PDF"))

    def test_second_call_overwrites_the_same_file_with_new_content(self):
        _atomic_write_pdf("<html><body>Version A</body></html>", self.output_path)
        first_bytes = self.output_path.read_bytes()

        _atomic_write_pdf(
            "<html><body>Version B with much more different text content here</body></html>",
            self.output_path,
        )
        second_bytes = self.output_path.read_bytes()

        self.assertNotEqual(first_bytes, second_bytes)
        tmp_path = self.output_path.with_name(self.output_path.name + ".tmp")
        self.assertFalse(tmp_path.exists())

    def test_failed_render_leaves_the_previous_file_untouched(self):
        _atomic_write_pdf("<html><body>Version A</body></html>", self.output_path)
        original_bytes = self.output_path.read_bytes()

        with patch("app.reports.report_pdf.HTML") as mock_html:
            mock_html.return_value.write_pdf.side_effect = RuntimeError("boom")
            with self.assertRaises(RuntimeError):
                _atomic_write_pdf("<html><body>Version B</body></html>", self.output_path)

        self.assertEqual(self.output_path.read_bytes(), original_bytes)
        tmp_path = self.output_path.with_name(self.output_path.name + ".tmp")
        self.assertFalse(tmp_path.exists())

    def test_failed_replace_leaves_the_previous_file_untouched(self):
        _atomic_write_pdf("<html><body>Version A</body></html>", self.output_path)
        original_bytes = self.output_path.read_bytes()

        with patch("app.reports.report_pdf.os.replace") as mock_replace:
            mock_replace.side_effect = PermissionError("boom")
            with self.assertRaises(PermissionError):
                _atomic_write_pdf("<html><body>Version B</body></html>", self.output_path)

        self.assertEqual(self.output_path.read_bytes(), original_bytes)
        tmp_path = self.output_path.with_name(self.output_path.name + ".tmp")
        self.assertFalse(tmp_path.exists())


if __name__ == "__main__":
    unittest.main()
