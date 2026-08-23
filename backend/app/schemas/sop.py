"""Pydantic schemas for the standalone SOP library — see
docs/superpowers/specs/2026-08-13-machines-sop-real-data-design.md. No tie to
any failure-mode taxonomy and not scoped to a machine_id (global library)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SopStepIn(BaseModel):
    id: str
    text: str
    priority: Literal["segera", "terjadwal"]
    estimated_minutes: int = Field(ge=0)


class SopStepOut(BaseModel):
    id: str
    text: str
    priority: Literal["segera", "terjadwal"]
    estimated_minutes: int


class SopOut(BaseModel):
    id: str
    title: str
    symptoms: str
    body: str
    steps: list[SopStepOut]
    reference: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def _stringify_id(cls, v: object) -> str:
        """Sop.id is a native uuid.UUID from SQLAlchemy (UUID(as_uuid=True))
        — Pydantic v2's plain `str` type doesn't auto-coerce that (unlike
        v1), so list_sops/create_sop/update_sop (routes_sop.py, which return
        the ORM object directly) raised ResponseValidationError as soon as a
        row existed. Never caught earlier because the table started empty."""
        return str(v)


class SopCreateIn(BaseModel):
    title: str
    symptoms: str = ""
    body: str = ""
    steps: list[SopStepIn] = Field(default_factory=list)
    reference: str = ""


class SopUpdateIn(BaseModel):
    title: str | None = None
    symptoms: str | None = None
    body: str | None = None
    steps: list[SopStepIn] | None = None
    reference: str | None = None
