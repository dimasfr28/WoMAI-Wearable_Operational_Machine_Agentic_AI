"""Pydantic schemas for the standalone SOP library — see
docs/superpowers/specs/2026-08-13-machines-sop-real-data-design.md. No tie to
any failure-mode taxonomy and not scoped to a machine_id (global library)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
