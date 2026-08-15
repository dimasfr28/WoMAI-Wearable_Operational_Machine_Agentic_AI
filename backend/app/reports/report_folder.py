"""On-disk folder scheme for Machine Report PDFs (rancangan.txt Section 7:
"buatkan skema folder, jadi setiap hari ada folder sendiri") — mirrors
app/ingestion/pdf_library.py's pattern (settings-driven root, per-machine
namespacing) but adds a per-day subfolder under each machine.

Layout: {REPORTS_DIR}/{machine_id}/{YYYY-MM-DD}/{report_number}.pdf
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings


def reports_dir() -> Path:
    path = Path(settings.REPORTS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def day_dir(machine_id: str, report_date: date) -> Path:
    path = reports_dir() / str(machine_id) / report_date.isoformat()
    path.mkdir(parents=True, exist_ok=True)
    return path


def report_path(machine_id: str, report_date: date, report_number: str) -> Path:
    return day_dir(machine_id, report_date) / f"{report_number}.pdf"


def relative_path(machine_id: str, report_date: date, report_number: str) -> str:
    """Value stored in MachineReport.file_path — relative to reports_dir()."""
    return f"{machine_id}/{report_date.isoformat()}/{report_number}.pdf"


def resolve(relative_file_path: str) -> Path:
    return reports_dir() / relative_file_path


def next_report_number(db: Session, machine_id: str, report_date: date) -> str:
    """"RPT-YYYYMMDD-NNN", sequence resets daily, GLOBAL across machines (not
    per-machine) — matches the example format in rancangan.txt
    ("RPT-20260528-001") which has no machine segment, so two machines
    generating a report on the same day get distinct sequence numbers from a
    single shared counter, not two separate "001"s. Race-safe enough for this
    system's actual write pattern (one report per POST /sensor/readings,
    already serialized by that request's own DB transaction)."""
    from app.db.models import MachineReport

    date_str = report_date.strftime("%Y%m%d")
    prefix = f"RPT-{date_str}-"
    count_today = (
        db.query(func.count(MachineReport.id))
        .filter(MachineReport.report_number.like(f"{prefix}%"))
        .scalar()
        or 0
    )
    return f"{prefix}{count_today + 1:03d}"


def today_utc() -> date:
    return datetime.now(timezone.utc).date()
