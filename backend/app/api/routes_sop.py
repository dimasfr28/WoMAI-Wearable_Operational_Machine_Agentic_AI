"""SOP library — standalone from any failure-mode taxonomy or machine scope,
see docs/superpowers/specs/2026-08-13-machines-sop-real-data-design.md.

GET /sops          — public (matches this codebase's existing pattern where
                      most read-only GETs are unauthenticated)
POST /sops          — require_role("engineer")
PATCH /sops/{id}    — require_role("engineer")
DELETE /sops/{id}   — require_role("engineer")
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.models import Sop, User
from app.db.session import get_db
from app.schemas.sop import SopCreateIn, SopOut, SopUpdateIn

router = APIRouter(prefix="/sops", tags=["sops"])


def _to_out(sop: Sop) -> SopOut:
    # SopOut.id is `str`, but Sop.id is a UUID column — pydantic v2 doesn't
    # coerce UUID -> str automatically, so from_attributes on the raw ORM
    # object raises ResponseValidationError. Convert explicitly instead.
    return SopOut(
        id=str(sop.id),
        title=sop.title,
        symptoms=sop.symptoms,
        body=sop.body,
        steps=sop.steps,
        reference=sop.reference,
        created_at=sop.created_at,
        updated_at=sop.updated_at,
    )


@router.get("", response_model=list[SopOut])
def list_sops(db: Session = Depends(get_db)):
    sops = db.query(Sop).order_by(Sop.created_at.asc()).all()
    return [_to_out(s) for s in sops]


@router.post("", response_model=SopOut, status_code=201)
def create_sop(
    payload: SopCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("engineer")),
):
    sop = Sop(
        title=payload.title,
        symptoms=payload.symptoms,
        body=payload.body,
        steps=[s.model_dump() for s in payload.steps],
        reference=payload.reference,
        created_by=user.id,
    )
    db.add(sop)
    db.commit()
    db.refresh(sop)
    return _to_out(sop)


@router.patch("/{sop_id}", response_model=SopOut)
def update_sop(
    sop_id: str,
    payload: SopUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("engineer")),
):
    sop = db.query(Sop).filter(Sop.id == sop_id).first()
    if sop is None:
        raise HTTPException(status_code=404, detail="SOP not found")
    if payload.title is not None:
        sop.title = payload.title
    if payload.symptoms is not None:
        sop.symptoms = payload.symptoms
    if payload.body is not None:
        sop.body = payload.body
    if payload.steps is not None:
        sop.steps = [s.model_dump() for s in payload.steps]
    if payload.reference is not None:
        sop.reference = payload.reference
    db.commit()
    db.refresh(sop)
    return _to_out(sop)


@router.delete("/{sop_id}", status_code=204)
def delete_sop(
    sop_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("engineer")),
):
    sop = db.query(Sop).filter(Sop.id == sop_id).first()
    if sop is None:
        raise HTTPException(status_code=404, detail="SOP not found")
    db.delete(sop)
    db.commit()
