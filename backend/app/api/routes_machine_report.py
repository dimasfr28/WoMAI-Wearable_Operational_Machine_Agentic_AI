"""Machine Report (rancangan.txt Section 7) — GET /machine-report/latest,
GET /machine-report/history, GET /machine-report/{id}/pdf.

PDFs themselves are generated once, automatically, inside
routes_report.py's _run_report_pipeline() every time a new sensor reading
comes in (see _generate_machine_report_pdf()) — this router is purely a
read path over the already-rendered files + MachineReport rows, mirroring
GET /report/latest's "no recomputation on GET" design.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.routes_report import regenerate_machine_report_pdf
from app.db.models import MachineReport
from app.db.session import get_db
from app.reports import report_folder
from app.schemas.machine_report import MachineReportOut

router = APIRouter(prefix="/machine-report", tags=["machine-report"])


def _to_out(report: MachineReport) -> MachineReportOut:
    return MachineReportOut(
        id=str(report.id),
        report_number=report.report_number,
        operating_status=report.operating_status,
        created_at=report.created_at,
    )


@router.get("/history", response_model=list[MachineReportOut])
def list_machine_reports(machine_id: str, db: Session = Depends(get_db), limit: int = 30):
    reports = (
        db.query(MachineReport)
        .filter(MachineReport.machine_id == machine_id)
        .order_by(MachineReport.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_to_out(r) for r in reports]


@router.get("/latest", response_model=MachineReportOut)
def get_latest_machine_report(machine_id: str, db: Session = Depends(get_db)):
    report = (
        db.query(MachineReport)
        .filter(MachineReport.machine_id == machine_id)
        .order_by(MachineReport.created_at.desc())
        .first()
    )
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="No Machine Report yet for this machine. Submit sensor data first.",
        )
    return _to_out(report)


def _serve_pdf(report: MachineReport, db: Session) -> FileResponse:
    pdf_path = report_folder.resolve(report.file_path)
    if not pdf_path.is_file():
        # File missing but the DB row (and the prediction/reading/final_report
        # it points at) may still be intact — this happens when REPORTS_DIR's
        # volume gets cleared independently of the DB (see commit 67e8eee).
        # Try to rebuild the PDF from already-persisted data before giving up.
        regenerated = regenerate_machine_report_pdf(db, report)
        if not regenerated or not pdf_path.is_file():
            raise HTTPException(
                status_code=404,
                detail=(
                    f"PDF file for report {report.report_number} was not found on disk "
                    "and could not be regenerated (source data is also missing)."
                ),
            )
    # `filename=` alone makes FileResponse default to
    # `Content-Disposition: attachment` (forces a download) — this endpoint
    # backs an in-page PDF viewer (frontend's Machine Report page), so it
    # must be `inline` instead; the explicit header below overrides that
    # default while still naming the file for the rare case a user does
    # save it (e.g. right-click "Save As" in the viewer).
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{report.report_number}.pdf"'},
    )


@router.get("/latest/pdf")
def get_latest_machine_report_pdf(machine_id: str, db: Session = Depends(get_db)):
    report = (
        db.query(MachineReport)
        .filter(MachineReport.machine_id == machine_id)
        .order_by(MachineReport.created_at.desc())
        .first()
    )
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="No Machine Report yet for this machine. Submit sensor data first.",
        )
    return _serve_pdf(report, db)


@router.get("/{report_id}/pdf")
def get_machine_report_pdf(report_id: str, db: Session = Depends(get_db)):
    report = db.query(MachineReport).filter(MachineReport.id == report_id).first()
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return _serve_pdf(report, db)
