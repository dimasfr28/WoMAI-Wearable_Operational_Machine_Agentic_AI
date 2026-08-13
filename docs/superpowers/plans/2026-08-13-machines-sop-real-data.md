# Machines & SOP Real Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the in-memory dummy Machines/SOP stores in the frontend with real backend calls — add missing `PATCH`/`DELETE /machines` endpoints, build a brand-new SOP library feature in the backend (migration + model + schema + routes), and wire both into the frontend with corrected data shapes.

**Architecture:** Backend gets two additive changes: new Machine mutation endpoints on the existing `machines` table, and an entirely new `sops` table/feature (global, no failure-mode taxonomy, no machine scoping). Frontend Server Actions (`actions/machines.ts`, `actions/sop.ts`) swap their in-memory arrays for real `fetch()` calls through a new shared `backendFetch()` helper that centralizes the JWT-cookie-to-Authorization-header handling and 401/403 error behavior already established in `actions/auth.ts`.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic (backend); Next.js Server Actions, Vitest (frontend).

## Global Constraints

- Machine schema in the frontend must match the REAL backend shape (`name`, `machine_type` free text, `status`, `document_count`, `run_count`) — not the AI4I-derived `type`/`line`/`notes` fields the dummy data used.
- SOP has NO `mode`/failure-taxonomy field and is NOT scoped to a `machine_id` — it's a global, standalone library.
- SOP `steps` stored as JSONB (matches the existing `Recommendation.payload` JSONB pattern in this codebase) — not a separate child table.
- All new/modified mutation endpoints (`PATCH`/`DELETE /machines/{id}`, `POST`/`PATCH`/`DELETE /sops`) require `require_role("engineer")` — matches the existing convention (`POST /machines`, knowledgebase upload/delete).
- `GET /sops` is public (no auth) — matches this codebase's existing convention for read-only GETs.
- `DELETE /machines/{id}` must return `409 Conflict` (not cascade-delete) if the machine still has related `documents` or `sensor_runs`.
- Exported Server Action function names/signatures (`loadMachinesAction`, `saveMachineAction`, etc.) stay the same so `lib/machines.ts`/`lib/sops.ts` callers don't need to change beyond their own inline parameter types (which DO need updating — they embed the old field names).
- Backend has no test suite/pytest infrastructure (confirmed: no `pytest` in `requirements.txt`, no test files) — backend verification is static (code review, response_model/RBAC checks) or manual (`curl`/Swagger) if a real Docker+`.env` environment is available, not automated pytest.
- comfest-18's ML prediction is binary (`predicted_label: bool`, explained via SHAP) — there is no `TWF`/`HDF`/`PWF`/`OSF`/`RNF` failure-mode concept anywhere in this backend to reference.

---

### Task 1: Backend — add Machine update/delete endpoints

**Files:**
- Modify: `backend/app/schemas/machine.py`
- Modify: `backend/app/api/routes_machine.py`

**Interfaces:**
- Produces: `PATCH /machines/{id}` (body: `{name?, machine_type?}`, response: `MachineOut`, role `engineer`+), `DELETE /machines/{id}` (204 on success, 409 if machine has related documents/sensor_runs, role `engineer`+). Frontend Task 4 calls these.

- [ ] **Step 1: Add `MachineUpdateIn` schema**

In `backend/app/schemas/machine.py`, find:
```python
class MachineCreateIn(BaseModel):
    name: str
    machine_type: str | None = None
```
Add immediately after it:
```python


class MachineUpdateIn(BaseModel):
    name: str | None = None
    machine_type: str | None = None
```

- [ ] **Step 2: Import `MachineUpdateIn` in the routes file**

In `backend/app/api/routes_machine.py`, find:
```python
from app.schemas.machine import EarlyWarningOut, EarlyWarningPanelOut, MachineCreateIn, MachineOut, MachineStatusOut
```
Replace with:
```python
from app.schemas.machine import (
    EarlyWarningOut,
    EarlyWarningPanelOut,
    MachineCreateIn,
    MachineOut,
    MachineStatusOut,
    MachineUpdateIn,
)
```

- [ ] **Step 3: Add the `PATCH` and `DELETE` endpoints**

In `backend/app/api/routes_machine.py`, find the end of `get_machine`:
```python
@router.get("/{machine_id}", response_model=MachineOut)
def get_machine(machine_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if machine is None:
        raise HTTPException(status_code=404, detail="Mesin tidak ditemukan")
    doc_count = db.query(Document).filter(Document.machine_id == machine.id).count()
    run_count = db.query(SensorRun).filter(SensorRun.machine_id == machine.id).count()
    return MachineOut(
        id=str(machine.id),
        name=machine.name,
        machine_type=machine.machine_type,
        status=machine.status,
        created_at=machine.created_at,
        document_count=doc_count,
        run_count=run_count,
    )
```
Add immediately after it (before the `# feature_name` comment block that follows):
```python


@router.patch("/{machine_id}", response_model=MachineOut)
def update_machine(
    machine_id: str,
    payload: MachineUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("engineer")),
):
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if machine is None:
        raise HTTPException(status_code=404, detail="Mesin tidak ditemukan")
    if payload.name is not None:
        machine.name = payload.name
    if payload.machine_type is not None:
        machine.machine_type = payload.machine_type
    db.commit()
    db.refresh(machine)
    doc_count = db.query(Document).filter(Document.machine_id == machine.id).count()
    run_count = db.query(SensorRun).filter(SensorRun.machine_id == machine.id).count()
    return MachineOut(
        id=str(machine.id),
        name=machine.name,
        machine_type=machine.machine_type,
        status=machine.status,
        created_at=machine.created_at,
        document_count=doc_count,
        run_count=run_count,
    )


@router.delete("/{machine_id}", status_code=204)
def delete_machine(
    machine_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("engineer")),
):
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if machine is None:
        raise HTTPException(status_code=404, detail="Mesin tidak ditemukan")
    doc_count = db.query(Document).filter(Document.machine_id == machine.id).count()
    run_count = db.query(SensorRun).filter(SensorRun.machine_id == machine.id).count()
    if doc_count > 0 or run_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Mesin masih punya {doc_count} dokumen dan {run_count} sensor run — hapus data terkait dulu.",
        )
    db.delete(machine)
    db.commit()
```

- [ ] **Step 4: Verify the file compiles (static check, no live server needed)**

Run: `python3 -c "import ast; ast.parse(open('backend/app/api/routes_machine.py').read())" && echo "OK"` (run from the repo root; adjust the path if your shell's cwd differs)
Expected: `OK` — confirms valid Python syntax. Full import-time verification requires the backend's Docker environment (heavy build, not always available — see Global Constraints); if you have a running backend, additionally verify with `docker compose exec backend python -c "from app.api.routes_machine import router; print([r.path for r in router.routes])"` and confirm `/machines/{machine_id}` appears with both `PATCH` and `DELETE` methods.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/machine.py backend/app/api/routes_machine.py
git commit -m "feat(backend): add PATCH/DELETE /machines/{id} endpoints"
```

---

### Task 2: Backend — SOP library feature (migration, model, schemas, routes)

**Files:**
- Create: `backend/app/db/migrations/versions/0010_sop_library.py`
- Modify: `backend/app/db/models.py`
- Create: `backend/app/schemas/sop.py`
- Create: `backend/app/api/routes_sop.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Produces: `GET /sops` (public, `list[SopOut]`), `POST /sops` (`SopCreateIn` → `SopOut`, 201, role `engineer`+), `PATCH /sops/{id}` (`SopUpdateIn` → `SopOut`, role `engineer`+), `DELETE /sops/{id}` (204, role `engineer`+). `SopOut` shape: `{id, title, symptoms, body, steps: [{id, text, priority: "segera"|"terjadwal", estimated_minutes}], reference, created_at, updated_at}`. Frontend Task 5 calls these.

- [ ] **Step 1: Create the migration**

Create `backend/app/db/migrations/versions/0010_sop_library.py`:
```python
"""add sops table — structured SOP library (title/symptoms/body/steps/reference).
Standalone from any failure-mode taxonomy (comfest-18's ML prediction is binary,
explained via SHAP feature importance — there is no TWF/HDF/PWF/OSF/RNF concept
in this backend) and from the existing PDF knowledgebase/CRAG system. Global
across all machines, not scoped to machine_id — see
docs/superpowers/specs/2026-08-13-machines-sop-real-data-design.md.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sops",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("symptoms", sa.Text(), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("steps", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("reference", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("sops")
```

- [ ] **Step 2: Add the `Sop` model**

In `backend/app/db/models.py`, the file ends with the `AgentToolLog` class (find its last line):
```python
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```
This is the last content in the file. Add after it:
```python


# ---------------------------------------------------------------------------
# SOP library (2026-08-13) — standalone structured procedure library, not
# tied to a failure-mode taxonomy or a specific machine.
# ---------------------------------------------------------------------------


class Sop(Base):
    __tablename__ = "sops"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    symptoms: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    reference: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```
Note: `JSONB`, `UUID`, `ForeignKey`, `String`, `Text`, `DateTime`, `Mapped`, `mapped_column`, `func`, `gen_uuid`, `Base` are all already imported/defined earlier in this file (used by other models) — no new imports needed for this step.

- [ ] **Step 3: Create the SOP schemas**

Create `backend/app/schemas/sop.py`:
```python
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
```

- [ ] **Step 4: Create the SOP routes**

Create `backend/app/api/routes_sop.py`:
```python
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


@router.get("", response_model=list[SopOut])
def list_sops(db: Session = Depends(get_db)):
    return db.query(Sop).order_by(Sop.created_at.asc()).all()


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
    return sop


@router.patch("/{sop_id}", response_model=SopOut)
def update_sop(
    sop_id: str,
    payload: SopUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("engineer")),
):
    sop = db.query(Sop).filter(Sop.id == sop_id).first()
    if sop is None:
        raise HTTPException(status_code=404, detail="SOP tidak ditemukan")
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
    return sop


@router.delete("/{sop_id}", status_code=204)
def delete_sop(
    sop_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("engineer")),
):
    sop = db.query(Sop).filter(Sop.id == sop_id).first()
    if sop is None:
        raise HTTPException(status_code=404, detail="SOP tidak ditemukan")
    db.delete(sop)
    db.commit()
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, find:
```python
from app.api.routes_auth import router as auth_router
from app.api.routes_knowledgebase import router as knowledgebase_router
from app.api.routes_machine import router as machine_router
from app.api.routes_report import router as report_router
from app.api.routes_sensor import router as sensor_router
```
Replace with:
```python
from app.api.routes_auth import router as auth_router
from app.api.routes_knowledgebase import router as knowledgebase_router
from app.api.routes_machine import router as machine_router
from app.api.routes_report import router as report_router
from app.api.routes_sensor import router as sensor_router
from app.api.routes_sop import router as sop_router
```
Then find:
```python
app.include_router(auth_router)
app.include_router(machine_router)
app.include_router(knowledgebase_router)
app.include_router(sensor_router)
app.include_router(report_router)
```
Replace with:
```python
app.include_router(auth_router)
app.include_router(machine_router)
app.include_router(knowledgebase_router)
app.include_router(sensor_router)
app.include_router(report_router)
app.include_router(sop_router)
```

- [ ] **Step 6: Static verification**

Run (from the repo root):
```bash
python3 -c "import ast; ast.parse(open('backend/app/db/migrations/versions/0010_sop_library.py').read())" && echo "migration OK"
python3 -c "import ast; ast.parse(open('backend/app/db/models.py').read())" && echo "models OK"
python3 -c "import ast; ast.parse(open('backend/app/schemas/sop.py').read())" && echo "schemas OK"
python3 -c "import ast; ast.parse(open('backend/app/api/routes_sop.py').read())" && echo "routes OK"
python3 -c "import ast; ast.parse(open('backend/app/main.py').read())" && echo "main OK"
```
Expected: all five print `OK`. If a real backend Docker environment is available, additionally run `docker compose exec backend alembic upgrade head` and confirm it applies revision `0010` without error, then `docker compose exec backend python -c "from app.api.routes_sop import router; print([r.path for r in router.routes])"` and confirm `/sops` and `/sops/{sop_id}` both appear.

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/migrations/versions/0010_sop_library.py backend/app/db/models.py backend/app/schemas/sop.py backend/app/api/routes_sop.py backend/app/main.py
git commit -m "feat(backend): add standalone SOP library (migration, model, schemas, routes)"
```

---

### Task 3: Frontend — update `Machine` and `Sop` types

**Files:**
- Modify: `frontend/src/lib/types.ts`

**Interfaces:**
- Produces: `Machine { id, name, machineType?, status, documentCount, runCount, createdAt }`; `Sop { id, title, symptoms, body, steps: SopStep[], reference, createdAt, updatedAt }` (unchanged `SopStep`). `SopMode` and `SOP_MODE_LABEL` are removed entirely. Tasks 4-7 depend on these exact shapes.

- [ ] **Step 1: Update the `Machine` interface**

In `frontend/src/lib/types.ts`, find:
```ts
export interface Machine {
  id: string;
  name: string;
  type: "L" | "M" | "H";
  line?: string;
  notes?: string;
  createdAt: string; // ISO
}
```
Replace with:
```ts
export interface Machine {
  id: string;
  name: string;
  machineType?: string; // free-text label, e.g. "Haas" — comfest-18 has no L/M/H concept
  status: string; // e.g. "running" — comfest-18's real Machine.status column
  documentCount: number;
  runCount: number;
  createdAt: string; // ISO
}
```

- [ ] **Step 2: Remove `SopMode`/`SOP_MODE_LABEL`, update `Sop`**

In `frontend/src/lib/types.ts`, find:
```ts
// Failure mode yang dicakup knowledge base SOP (selaras AI4I 2020 & backend).
export type SopMode = "TWF" | "HDF" | "PWF" | "OSF" | "RNF";

export const SOP_MODE_LABEL: Record<SopMode, string> = {
  TWF: "Tool Wear Failure",
  HDF: "Heat Dissipation Failure",
  PWF: "Power Failure",
  OSF: "Overstrain Failure",
  RNF: "Random Failure",
};

// Dokumen SOP terkurasi — knowledge base global yang dipakai pipeline retrieval.
export interface Sop {
  id: string;
  mode: SopMode;
  title: string;
  symptoms: string; // kata kunci gejala (dipakai embedding retrieval)
  body: string; // deskripsi + tindakan (teks yang di-embed)
  steps: SopStep[];
  reference: string;
  createdAt: string; // ISO
  updatedAt: string; // ISO
}
```
Replace with:
```ts
// SOP library mandiri — TIDAK terikat failure-mode taxonomy apa pun (backend
// comfest-18 tidak punya konsep itu; prediksinya biner, dijelaskan SHAP
// per-fitur sensor) dan TIDAK di-scope per mesin (global).
export interface Sop {
  id: string;
  title: string;
  symptoms: string; // kata kunci gejala (dipakai pencarian)
  body: string; // deskripsi + tindakan
  steps: SopStep[];
  reference: string;
  createdAt: string; // ISO
  updatedAt: string; // ISO
}
```

- [ ] **Step 3: Verify no other file still references the removed symbols**

Run: `grep -rln "SopMode\|SOP_MODE_LABEL" frontend/src`
Expected: no output yet (Tasks 6-7 haven't updated their consumers), so this WILL show `sop-form-dialog.tsx` and `sop/page.tsx` at this point — that's expected, they're fixed in Task 7. Just confirm `frontend/src/lib/types.ts` itself no longer defines them (`grep -n "SopMode\|SOP_MODE_LABEL" frontend/src/lib/types.ts` should show no output).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts
git commit -m "feat(frontend): update Machine/Sop types to match real backend schema"
```

---

### Task 4: Frontend — wire `machines.ts` to the real backend

**Files:**
- Create: `frontend/src/lib/backend-fetch.ts`
- Create: `frontend/src/lib/backend-fetch.test.ts`
- Modify: `frontend/src/app/actions/machines.ts` (full rewrite)
- Create: `frontend/src/app/actions/machines.test.ts`
- Modify: `frontend/src/lib/machines.ts`

**Interfaces:**
- Consumes: `Machine` type from Task 3; `requireSession()`, `clearSessionCookie()` from `@/lib/auth/session` (existing, from sub-project 1).
- Produces: `backendFetch(path: string, init?: RequestInit): Promise<Response>` in `lib/backend-fetch.ts` — attaches `Authorization: Bearer <token>`, clears the session cookie and redirects to `/login` on 401, throws `Error("Aksi ini butuh role engineer atau lebih tinggi.")` on 403, otherwise returns the response unchanged. Task 5 (sop.ts) reuses this same helper. `loadMachinesAction()`, `getMachineAction(id)`, `saveMachineAction(input: {id?, name, machineType?})`, `deleteMachineAction(id)` in `machines.ts` — same names as before, new signature for `saveMachineAction`'s input (drops `type`/`line`/`notes`, adds `machineType?`).

- [ ] **Step 1: Write the failing test for `backendFetch`**

Create `frontend/src/lib/backend-fetch.test.ts`:
```ts
import { beforeEach, describe, expect, it, vi } from "vitest";

const cookieStore = new Map<string, string>();

vi.mock("server-only", () => ({}));

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      cookieStore.has(name) ? { name, value: cookieStore.get(name)! } : undefined,
    set: (name: string, value: string) => {
      cookieStore.set(name, value);
    },
    delete: (name: string) => {
      cookieStore.delete(name);
    },
  }),
}));

vi.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`REDIRECT:${path}`);
  },
}));

import { backendFetch } from "./backend-fetch";

describe("backendFetch", () => {
  beforeEach(() => {
    cookieStore.clear();
    cookieStore.set("womai_session", "tok123");
    vi.restoreAllMocks();
  });

  it("attaches the Authorization header from the session cookie", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await backendFetch("/machines");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/machines"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
      }),
    );
  });

  it("clears the session cookie and redirects to /login on 401", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
    );
    await expect(backendFetch("/machines")).rejects.toThrow("REDIRECT:/login");
    expect(cookieStore.has("womai_session")).toBe(false);
  });

  it("throws a role-specific message on 403", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 403 })),
    );
    await expect(backendFetch("/machines")).rejects.toThrow(
      "Aksi ini butuh role engineer atau lebih tinggi.",
    );
  });

  it("returns the response unchanged for other statuses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 404 })),
    );
    const resp = await backendFetch("/machines/x");
    expect(resp.status).toBe(404);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && bun run test backend-fetch.test.ts`
Expected: FAIL — `./backend-fetch` module not found.

- [ ] **Step 3: Implement `backendFetch`**

Create `frontend/src/lib/backend-fetch.ts`:
```ts
import "server-only";
import { redirect } from "next/navigation";
import { clearSessionCookie, requireSession } from "@/lib/auth/session";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8002";

/**
 * fetch() ke backend comfest-18 dengan header Authorization Bearer dari sesi
 * aktif. 401 (token invalid/kadaluarsa) -> hapus cookie sesi & redirect ke
 * /login. 403 (role kurang) -> lempar Error dengan pesan jelas untuk
 * ditampilkan sebagai toast. Response non-2xx lain dikembalikan apa adanya —
 * pemanggil yang menentukan pesan error spesifik per endpoint.
 */
export async function backendFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const token = await requireSession();
  const resp = await fetch(`${BACKEND_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${token}`,
    },
  });

  if (resp.status === 401) {
    await clearSessionCookie();
    redirect("/login");
  }
  if (resp.status === 403) {
    throw new Error("Aksi ini butuh role engineer atau lebih tinggi.");
  }
  return resp;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && bun run test backend-fetch.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Write the failing test for `machines.ts`**

Create `frontend/src/app/actions/machines.test.ts`:
```ts
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/backend-fetch", () => ({
  backendFetch: vi.fn(),
}));

import { backendFetch } from "@/lib/backend-fetch";
import {
  deleteMachineAction,
  getMachineAction,
  loadMachinesAction,
  saveMachineAction,
} from "./machines";

const mockedBackendFetch = vi.mocked(backendFetch);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("loadMachinesAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("maps snake_case backend fields to camelCase Machine objects", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse([
        {
          id: "m-1",
          name: "CNC Mill",
          machine_type: "Haas",
          status: "running",
          created_at: "2026-08-01T00:00:00Z",
          document_count: 2,
          run_count: 5,
        },
      ]),
    );
    const result = await loadMachinesAction();
    expect(result).toEqual([
      {
        id: "m-1",
        name: "CNC Mill",
        machineType: "Haas",
        status: "running",
        documentCount: 2,
        runCount: 5,
        createdAt: "2026-08-01T00:00:00Z",
      },
    ]);
    expect(mockedBackendFetch).toHaveBeenCalledWith(
      "/machines",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("throws when the backend responds with a non-ok status", async () => {
    mockedBackendFetch.mockResolvedValue(jsonResponse({}, 500));
    await expect(loadMachinesAction()).rejects.toThrow(
      "Gagal memuat daftar mesin (500)",
    );
  });
});

describe("getMachineAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("returns null on 404", async () => {
    mockedBackendFetch.mockResolvedValue(jsonResponse({}, 404));
    const result = await getMachineAction("missing");
    expect(result).toBeNull();
  });
});

describe("saveMachineAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("POSTs to /machines when creating (no id)", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse({
        id: "m-2",
        name: "New Machine",
        machine_type: null,
        status: "running",
        created_at: "2026-08-01T00:00:00Z",
        document_count: 0,
        run_count: 0,
      }),
    );
    const result = await saveMachineAction({ name: "New Machine" });
    expect(mockedBackendFetch).toHaveBeenCalledWith(
      "/machines",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.machineType).toBeUndefined();
  });

  it("PATCHes to /machines/{id} when updating (id present)", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse({
        id: "m-1",
        name: "Renamed",
        machine_type: "Haas",
        status: "running",
        created_at: "2026-08-01T00:00:00Z",
        document_count: 0,
        run_count: 0,
      }),
    );
    await saveMachineAction({ id: "m-1", name: "Renamed", machineType: "Haas" });
    expect(mockedBackendFetch).toHaveBeenCalledWith(
      "/machines/m-1",
      expect.objectContaining({ method: "PATCH" }),
    );
  });
});

describe("deleteMachineAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("throws the backend's detail message on 409 (machine has related data)", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse(
        {
          detail:
            "Mesin masih punya 2 dokumen dan 1 sensor run — hapus data terkait dulu.",
        },
        409,
      ),
    );
    await expect(deleteMachineAction("m-1")).rejects.toThrow(
      "Mesin masih punya 2 dokumen dan 1 sensor run — hapus data terkait dulu.",
    );
  });
});
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `cd frontend && bun run test app/actions/machines.test.ts`
Expected: FAIL — current `machines.ts` doesn't call `backendFetch` at all (still in-memory), so the mocked calls never happen and assertions fail.

- [ ] **Step 7: Rewrite `machines.ts`**

Replace the entire content of `frontend/src/app/actions/machines.ts`:
```ts
"use server";

import { backendFetch } from "@/lib/backend-fetch";
import type { Machine } from "@/lib/types";

interface MachineApiOut {
  id: string;
  name: string;
  machine_type: string | null;
  status: string;
  created_at: string;
  document_count: number;
  run_count: number;
}

function fromApi(m: MachineApiOut): Machine {
  return {
    id: m.id,
    name: m.name,
    machineType: m.machine_type ?? undefined,
    status: m.status,
    documentCount: m.document_count,
    runCount: m.run_count,
    createdAt: m.created_at,
  };
}

export async function loadMachinesAction(): Promise<Machine[]> {
  const resp = await backendFetch("/machines", { cache: "no-store" });
  if (!resp.ok) {
    throw new Error(`Gagal memuat daftar mesin (${resp.status})`);
  }
  const data = (await resp.json()) as MachineApiOut[];
  return data.map(fromApi);
}

export async function getMachineAction(id: string): Promise<Machine | null> {
  const resp = await backendFetch(`/machines/${id}`, { cache: "no-store" });
  if (resp.status === 404) return null;
  if (!resp.ok) {
    throw new Error(`Gagal memuat mesin (${resp.status})`);
  }
  const data = (await resp.json()) as MachineApiOut;
  return fromApi(data);
}

export async function saveMachineAction(input: {
  id?: string;
  name: string;
  machineType?: string;
}): Promise<Machine> {
  const body = JSON.stringify({
    name: input.name,
    machine_type: input.machineType || null,
  });
  const resp = await backendFetch(
    input.id ? `/machines/${input.id}` : "/machines",
    {
      method: input.id ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body,
    },
  );
  if (!resp.ok) {
    throw new Error(`Gagal menyimpan mesin (${resp.status})`);
  }
  const data = (await resp.json()) as MachineApiOut;
  return fromApi(data);
}

export async function deleteMachineAction(id: string): Promise<void> {
  const resp = await backendFetch(`/machines/${id}`, { method: "DELETE" });
  if (!resp.ok) {
    const body = (await resp.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(body?.detail ?? `Gagal menghapus mesin (${resp.status})`);
  }
}
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `cd frontend && bun run test app/actions/machines.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 9: Fix `lib/machines.ts`'s `saveMachine` parameter type**

In `frontend/src/lib/machines.ts`, find:
```ts
export async function saveMachine(machine: {
  id?: string;
  name: string;
  type: Machine["type"];
  line?: string;
  notes?: string;
}): Promise<Machine> {
```
Replace with:
```ts
export async function saveMachine(machine: {
  id?: string;
  name: string;
  machineType?: string;
}): Promise<Machine> {
```

- [ ] **Step 10: Run the full test suite**

Run: `cd frontend && bun run test`
Expected: all suites pass, including the pre-existing ones from sub-project 1.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/lib/backend-fetch.ts frontend/src/lib/backend-fetch.test.ts frontend/src/app/actions/machines.ts frontend/src/app/actions/machines.test.ts frontend/src/lib/machines.ts
git commit -m "feat(frontend): wire machines.ts to the real backend via backendFetch"
```

---

### Task 5: Frontend — wire `sop.ts` to the real backend

**Files:**
- Modify: `frontend/src/app/actions/sop.ts` (full rewrite)
- Create: `frontend/src/app/actions/sop.test.ts`
- Modify: `frontend/src/lib/sops.ts`

**Interfaces:**
- Consumes: `backendFetch()` from Task 4's `lib/backend-fetch.ts`; `Sop`/`SopStep` types from Task 3.
- Produces: `loadSopsAction()`, `saveSopAction(input: {id?, title, symptoms, body, steps, reference})`, `deleteSopAction(id)` — same names as before, new signature for `saveSopAction`'s input (drops `mode`).

- [ ] **Step 1: Write the failing test for `sop.ts`**

Create `frontend/src/app/actions/sop.test.ts`:
```ts
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/backend-fetch", () => ({
  backendFetch: vi.fn(),
}));

import { backendFetch } from "@/lib/backend-fetch";
import { deleteSopAction, loadSopsAction, saveSopAction } from "./sop";

const mockedBackendFetch = vi.mocked(backendFetch);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("loadSopsAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("maps snake_case steps to camelCase SopStep objects", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse([
        {
          id: "sop-1",
          title: "Penanganan Overheat",
          symptoms: "suhu tinggi",
          body: "deskripsi",
          steps: [
            {
              id: "s-1",
              text: "Turunkan beban",
              priority: "segera",
              estimated_minutes: 10,
            },
          ],
          reference: "Rev.1",
          created_at: "2026-08-01T00:00:00Z",
          updated_at: "2026-08-01T00:00:00Z",
        },
      ]),
    );
    const result = await loadSopsAction();
    expect(result[0].steps).toEqual([
      { id: "s-1", text: "Turunkan beban", priority: "segera", estimatedMinutes: 10 },
    ]);
  });

  it("throws when the backend responds with a non-ok status", async () => {
    mockedBackendFetch.mockResolvedValue(jsonResponse({}, 500));
    await expect(loadSopsAction()).rejects.toThrow("Gagal memuat daftar SOP (500)");
  });
});

describe("saveSopAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("POSTs to /sops when creating and converts steps to snake_case in the request body", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse({
        id: "sop-2",
        title: "New SOP",
        symptoms: "",
        body: "",
        steps: [],
        reference: "",
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      }),
    );
    await saveSopAction({
      title: "New SOP",
      symptoms: "",
      body: "",
      reference: "",
      steps: [{ id: "s-1", text: "Step", priority: "segera", estimatedMinutes: 5 }],
    });
    expect(mockedBackendFetch).toHaveBeenCalledWith(
      "/sops",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          title: "New SOP",
          symptoms: "",
          body: "",
          steps: [{ id: "s-1", text: "Step", priority: "segera", estimated_minutes: 5 }],
          reference: "",
        }),
      }),
    );
  });

  it("PATCHes to /sops/{id} when updating", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse({
        id: "sop-1",
        title: "Updated",
        symptoms: "",
        body: "",
        steps: [],
        reference: "",
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      }),
    );
    await saveSopAction({
      id: "sop-1",
      title: "Updated",
      symptoms: "",
      body: "",
      reference: "",
      steps: [],
    });
    expect(mockedBackendFetch).toHaveBeenCalledWith(
      "/sops/sop-1",
      expect.objectContaining({ method: "PATCH" }),
    );
  });
});

describe("deleteSopAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("throws on non-ok response", async () => {
    mockedBackendFetch.mockResolvedValue(jsonResponse({}, 500));
    await expect(deleteSopAction("sop-1")).rejects.toThrow(
      "Gagal menghapus SOP (500)",
    );
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && bun run test app/actions/sop.test.ts`
Expected: FAIL — current `sop.ts` doesn't call `backendFetch`.

- [ ] **Step 3: Rewrite `sop.ts`**

Replace the entire content of `frontend/src/app/actions/sop.ts`:
```ts
"use server";

import { backendFetch } from "@/lib/backend-fetch";
import type { Sop, SopStep } from "@/lib/types";

interface SopStepApiOut {
  id: string;
  text: string;
  priority: "segera" | "terjadwal";
  estimated_minutes: number;
}

interface SopApiOut {
  id: string;
  title: string;
  symptoms: string;
  body: string;
  steps: SopStepApiOut[];
  reference: string;
  created_at: string;
  updated_at: string;
}

function fromApi(s: SopApiOut): Sop {
  return {
    id: s.id,
    title: s.title,
    symptoms: s.symptoms,
    body: s.body,
    steps: s.steps.map(
      (step): SopStep => ({
        id: step.id,
        text: step.text,
        priority: step.priority,
        estimatedMinutes: step.estimated_minutes,
      }),
    ),
    reference: s.reference,
    createdAt: s.created_at,
    updatedAt: s.updated_at,
  };
}

function toApiSteps(steps: SopStep[]) {
  return steps.map((s) => ({
    id: s.id,
    text: s.text,
    priority: s.priority,
    estimated_minutes: s.estimatedMinutes,
  }));
}

export async function loadSopsAction(): Promise<Sop[]> {
  const resp = await backendFetch("/sops", { cache: "no-store" });
  if (!resp.ok) {
    throw new Error(`Gagal memuat daftar SOP (${resp.status})`);
  }
  const data = (await resp.json()) as SopApiOut[];
  return data.map(fromApi);
}

export async function saveSopAction(input: {
  id?: string;
  title: string;
  symptoms: string;
  body: string;
  steps: SopStep[];
  reference: string;
}): Promise<Sop> {
  const payload = JSON.stringify({
    title: input.title,
    symptoms: input.symptoms,
    body: input.body,
    steps: toApiSteps(input.steps),
    reference: input.reference,
  });
  const resp = await backendFetch(input.id ? `/sops/${input.id}` : "/sops", {
    method: input.id ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
  });
  if (!resp.ok) {
    throw new Error(`Gagal menyimpan SOP (${resp.status})`);
  }
  const data = (await resp.json()) as SopApiOut;
  return fromApi(data);
}

export async function deleteSopAction(id: string): Promise<void> {
  const resp = await backendFetch(`/sops/${id}`, { method: "DELETE" });
  if (!resp.ok) {
    throw new Error(`Gagal menghapus SOP (${resp.status})`);
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && bun run test app/actions/sop.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Fix `lib/sops.ts`'s `saveSop` parameter type**

In `frontend/src/lib/sops.ts`, find:
```ts
import {
  deleteSopAction,
  loadSopsAction,
  saveSopAction,
} from "@/app/actions/sop";
import type { Sop, SopMode, SopStep } from "@/lib/types";
```
Replace with:
```ts
import {
  deleteSopAction,
  loadSopsAction,
  saveSopAction,
} from "@/app/actions/sop";
import type { Sop, SopStep } from "@/lib/types";
```
Then find:
```ts
export async function saveSop(sop: {
  id?: string;
  mode: SopMode;
  title: string;
  symptoms: string;
  body: string;
  steps: SopStep[];
  reference: string;
}): Promise<Sop> {
```
Replace with:
```ts
export async function saveSop(sop: {
  id?: string;
  title: string;
  symptoms: string;
  body: string;
  steps: SopStep[];
  reference: string;
}): Promise<Sop> {
```

- [ ] **Step 6: Run the full test suite**

Run: `cd frontend && bun run test`
Expected: all suites pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/actions/sop.ts frontend/src/app/actions/sop.test.ts frontend/src/lib/sops.ts
git commit -m "feat(frontend): wire sop.ts to the real backend via backendFetch"
```

---

### Task 6: Frontend — update Machine UI components

**Files:**
- Modify: `frontend/src/components/machine-form-dialog.tsx`
- Modify: `frontend/src/app/(app)/mesin/page.tsx`
- Modify: `frontend/src/components/chat/machine-picker.tsx`

**Interfaces:**
- Consumes: `Machine` type from Task 3, `saveMachine`/`deleteMachine` from `lib/machines.ts` (Task 4, unchanged call sites).

- [ ] **Step 1: Rewrite `machine-form-dialog.tsx`**

Replace the entire content of `frontend/src/components/machine-form-dialog.tsx`:
```tsx
"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { saveMachine } from "@/lib/machines";
import type { Machine } from "@/lib/types";

interface MachineFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  machine?: Machine;
  onSaved: (m: Machine) => void;
}

export function MachineFormDialog({
  open,
  onOpenChange,
  machine,
  onSaved,
}: MachineFormDialogProps) {
  const [name, setName] = useState("");
  const [machineType, setMachineType] = useState("");

  // Reset form when dialog opens; prefill from machine prop in edit mode
  useEffect(() => {
    if (!open) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setName(machine?.name ?? "");
    setMachineType(machine?.machineType ?? "");
  }, [open, machine]);

  const [saving, setSaving] = useState(false);
  const canSave = name.trim().length > 0 && !saving;

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    const trimmedType = machineType.trim();
    try {
      const saved = await saveMachine({
        id: machine?.id,
        name: name.trim(),
        machineType: trimmedType || undefined,
      });
      onSaved(saved);
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Gagal menyimpan mesin.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {machine ? "Edit Mesin" : "Tambah Mesin"}
          </DialogTitle>
          <DialogDescription>
            {machine
              ? "Perbarui informasi mesin."
              : "Tambahkan mesin baru ke daftar."}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="mesin-nama">
              Nama mesin <span className="text-destructive">*</span>
            </Label>
            <Input
              id="mesin-nama"
              placeholder="mis. CNC Mill 01"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="mesin-tipe">Tipe mesin (opsional)</Label>
            <Input
              id="mesin-tipe"
              placeholder="mis. Haas"
              value={machineType}
              onChange={(e) => setMachineType(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button type="button" onClick={handleSave} disabled={!canSave}>
            Simpan Mesin
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Rewrite `mesin/page.tsx`**

Replace the entire content of `frontend/src/app/(app)/mesin/page.tsx`:
```tsx
"use client";

import Link from "next/link";
import { useState } from "react";
import { Factory, MessageSquareText, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { MachineFormDialog } from "@/components/machine-form-dialog";
import { useMachines } from "@/hooks/use-machines";
import { useSessions } from "@/hooks/use-sessions";
import { deleteMachine } from "@/lib/machines";
import type { Machine } from "@/lib/types";
import { RISK_BADGE } from "@/lib/risk";
import { cn } from "@/lib/utils";

export default function MesinPage() {
  const { machines } = useMachines();
  const { sessions } = useSessions();
  const [addOpen, setAddOpen] = useState(false);
  const [editMachine, setEditMachine] = useState<Machine | undefined>(
    undefined,
  );

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 overflow-y-auto p-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold">Mesin</h1>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          Tambah Mesin
        </Button>
      </div>

      {machines.length === 0 ? (
        <div className="flex flex-col items-center gap-4 py-16">
          <Factory className="size-12 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Belum ada mesin terdaftar.
          </p>
          <Button onClick={() => setAddOpen(true)}>
            Tambah Mesin Pertama
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {machines.map((m) => {
            const machineSessions = sessions.filter(
              (s) => s.machineId === m.id,
            );
            const sessionCount = machineSessions.length;
            const lastPrediction = machineSessions.find(
              (s) => s.lastPrediction,
            )?.lastPrediction;

            return (
              <Card key={m.id} className="py-0">
                <CardContent className="flex flex-col gap-3 p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <span className="font-medium">{m.name}</span>
                      {m.machineType && (
                        <span className="text-xs text-muted-foreground">
                          {m.machineType}
                        </span>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <Badge variant="secondary">{m.status}</Badge>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setEditMachine(m)}
                      >
                        <Pencil className="size-4" />
                        <span className="sr-only">Edit mesin</span>
                      </Button>
                      <AlertDialog>
                        <AlertDialogTrigger
                          render={<Button variant="ghost" size="icon" />}
                        >
                          <Trash2 className="size-4" />
                          <span className="sr-only">Hapus mesin</span>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Hapus mesin?</AlertDialogTitle>
                            <AlertDialogDescription>
                              Mesin &quot;{m.name}&quot; akan dihapus. Sesi
                              lama yang sudah terekam tetap tersimpan dengan
                              nama mesin saat itu.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Batal</AlertDialogCancel>
                            <AlertDialogAction
                              onClick={async () => {
                                try {
                                  await deleteMachine(m.id);
                                  toast.success("Mesin dihapus.");
                                } catch (err) {
                                  toast.error(
                                    err instanceof Error
                                      ? err.message
                                      : "Gagal menghapus mesin.",
                                  );
                                }
                              }}
                            >
                              Hapus
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-muted-foreground">
                      {m.documentCount} dokumen · {m.runCount} run ·{" "}
                      {sessionCount} sesi
                    </span>
                    {lastPrediction ? (
                      <Badge
                        className={cn(RISK_BADGE[lastPrediction.riskLevel])}
                      >
                        {lastPrediction.failureType === "NONE"
                          ? "Normal"
                          : `${lastPrediction.failureType} · risiko ${lastPrediction.riskLevel}`}
                      </Badge>
                    ) : (
                      <Badge variant="secondary">Belum ada prediksi</Badge>
                    )}
                    {sessionCount > 0 && (
                      <Link
                        href={`/riwayat?mesin=${m.id}`}
                        className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                      >
                        <MessageSquareText className="size-3.5" />
                        Lihat sesi
                      </Link>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <MachineFormDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        onSaved={() => {}}
      />
      <MachineFormDialog
        open={editMachine !== undefined}
        onOpenChange={(o) => {
          if (!o) setEditMachine(undefined);
        }}
        machine={editMachine}
        onSaved={() => {}}
      />
    </div>
  );
}
```

- [ ] **Step 3: Fix `machine-picker.tsx`'s reference to the removed `type` field**

In `frontend/src/components/chat/machine-picker.tsx`, find:
```tsx
                {m.type}
```
Replace with:
```tsx
                {m.machineType ?? "Haas"}
```

- [ ] **Step 4: Verify no remaining references to the removed `Machine` fields**

Run: `grep -rn "\.type\b" frontend/src/components/machine-form-dialog.tsx frontend/src/app/\(app\)/mesin/page.tsx frontend/src/components/chat/machine-picker.tsx`
Expected: no output (or only unrelated matches like `type="button"`/`type="number"` HTML attributes — confirm any match is an HTML `type` attribute, not `Machine["type"]`, before treating this as passing).

- [ ] **Step 5: Run the frontend test suite and typecheck**

Run: `cd frontend && bunx tsc --noEmit`
Expected: no errors.
Run: `cd frontend && bun run test`
Expected: all suites pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/machine-form-dialog.tsx "frontend/src/app/(app)/mesin/page.tsx" frontend/src/components/chat/machine-picker.tsx
git commit -m "feat(frontend): update Machine UI for the real backend schema"
```

---

### Task 7: Frontend — update SOP UI components

**Files:**
- Modify: `frontend/src/components/sop-form-dialog.tsx`
- Modify: `frontend/src/app/(app)/sop/page.tsx`

**Interfaces:**
- Consumes: `Sop`/`SopStep` types from Task 3, `saveSop`/`deleteSop` from `lib/sops.ts` (Task 5, unchanged call sites).

- [ ] **Step 1: Rewrite `sop-form-dialog.tsx`**

Replace the entire content of `frontend/src/components/sop-form-dialog.tsx`:
```tsx
"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { saveSop } from "@/lib/sops";
import type { Sop, SopStep } from "@/lib/types";

interface SopFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sop?: Sop;
  onSaved: (s: Sop) => void;
}

function emptyStep(): SopStep {
  return {
    id:
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `step-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    text: "",
    priority: "segera",
    estimatedMinutes: 15,
  };
}

export function SopFormDialog({
  open,
  onOpenChange,
  sop,
  onSaved,
}: SopFormDialogProps) {
  const [title, setTitle] = useState("");
  const [symptoms, setSymptoms] = useState("");
  const [body, setBody] = useState("");
  const [reference, setReference] = useState("");
  const [steps, setSteps] = useState<SopStep[]>([]);

  // Reset saat dibuka; prefill dari prop sop di mode edit.
  useEffect(() => {
    if (!open) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTitle(sop?.title ?? "");
    setSymptoms(sop?.symptoms ?? "");
    setBody(sop?.body ?? "");
    setReference(sop?.reference ?? "");
    setSteps(sop?.steps.length ? sop.steps.map((s) => ({ ...s })) : [emptyStep()]);
  }, [open, sop]);

  const [saving, setSaving] = useState(false);
  const canSave = title.trim().length > 0 && body.trim().length > 0 && !saving;

  function updateStep(id: string, patch: Partial<SopStep>) {
    setSteps((prev) => prev.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  }

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    const cleanSteps = steps
      .filter((s) => s.text.trim().length > 0)
      .map((s) => ({
        ...s,
        text: s.text.trim(),
        estimatedMinutes: Math.max(0, Math.round(s.estimatedMinutes) || 0),
      }));
    try {
      const saved = await saveSop({
        id: sop?.id,
        title: title.trim(),
        symptoms: symptoms.trim(),
        body: body.trim(),
        reference: reference.trim(),
        steps: cleanSteps,
      });
      onSaved(saved);
      onOpenChange(false);
      toast.success(sop ? "SOP diperbarui." : "SOP ditambahkan.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Gagal menyimpan SOP.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{sop ? "Edit SOP" : "Tambah SOP"}</DialogTitle>
          <DialogDescription>
            Dokumen SOP jadi rujukan rekomendasi tindakan. Rekomendasi chatbot
            hanya diambil dari SOP yang tersimpan di sini.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="sop-title">
              Judul <span className="text-destructive">*</span>
            </Label>
            <Input
              id="sop-title"
              placeholder="mis. Penanganan Heat Dissipation Failure"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="sop-symptoms">Gejala / kata kunci</Label>
            <Textarea
              id="sop-symptoms"
              placeholder="mis. suhu proses tinggi, mesin panas, pembuangan panas tidak efektif"
              value={symptoms}
              onChange={(e) => setSymptoms(e.target.value)}
              rows={2}
              className="resize-none"
            />
            <p className="text-muted-foreground text-xs">
              Dipakai mesin pencari SOP untuk mencocokkan kondisi mesin.
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="sop-body">
              Deskripsi &amp; tindakan <span className="text-destructive">*</span>
            </Label>
            <Textarea
              id="sop-body"
              placeholder="Penjelasan penyebab + garis besar tindakan penanganan…"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={4}
              className="resize-none"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="sop-reference">Referensi</Label>
            <Input
              id="sop-reference"
              placeholder="mis. SOP Maintenance Termal - Rev.2"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
          </div>

          {/* Langkah tindakan */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label>Langkah tindakan</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setSteps((prev) => [...prev, emptyStep()])}
              >
                <Plus className="size-4" />
                Tambah langkah
              </Button>
            </div>
            <div className="flex flex-col gap-3">
              {steps.map((s, i) => (
                <div
                  key={s.id}
                  className="flex flex-col gap-2 rounded-lg border p-3"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground text-sm font-medium">
                      {i + 1}.
                    </span>
                    <Input
                      placeholder="Deskripsi langkah"
                      value={s.text}
                      onChange={(e) => updateStep(s.id, { text: e.target.value })}
                      className="flex-1"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() =>
                        setSteps((prev) => prev.filter((x) => x.id !== s.id))
                      }
                    >
                      <Trash2 className="size-4" />
                      <span className="sr-only">Hapus langkah</span>
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-2 pl-6">
                    <Select
                      value={s.priority}
                      onValueChange={(v) => {
                        if (v) updateStep(s.id, { priority: v as SopStep["priority"] });
                      }}
                    >
                      <SelectTrigger className="w-36">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="segera">Segera</SelectItem>
                        <SelectItem value="terjadwal">Terjadwal</SelectItem>
                      </SelectContent>
                    </Select>
                    <div className="flex items-center gap-1.5">
                      <Input
                        type="number"
                        min={0}
                        value={String(s.estimatedMinutes)}
                        onChange={(e) =>
                          updateStep(s.id, {
                            estimatedMinutes: Number(e.target.value),
                          })
                        }
                        className="w-20"
                      />
                      <span className="text-muted-foreground text-sm">menit</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button type="button" onClick={handleSave} disabled={!canSave}>
            Simpan SOP
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Rewrite `sop/page.tsx`**

Replace the entire content of `frontend/src/app/(app)/sop/page.tsx`:
```tsx
"use client";

import { useState } from "react";
import { FileText, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { SopFormDialog } from "@/components/sop-form-dialog";
import { useSops } from "@/hooks/use-sops";
import { deleteSop } from "@/lib/sops";
import type { Sop } from "@/lib/types";

export default function SopPage() {
  const { sops, loading } = useSops();
  const [addOpen, setAddOpen] = useState(false);
  const [editSop, setEditSop] = useState<Sop | undefined>(undefined);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 overflow-y-auto p-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <h1 className="text-xl font-semibold">SOP File</h1>
          <p className="text-muted-foreground text-sm">
            Knowledge base tindakan yang dipakai chatbot untuk merekomendasikan
            penanganan.
          </p>
        </div>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          Tambah SOP
        </Button>
      </div>

      {sops.length === 0 && !loading ? (
        <div className="flex flex-col items-center gap-4 py-16">
          <FileText className="text-muted-foreground size-12" />
          <p className="text-muted-foreground text-sm">Belum ada SOP tersimpan.</p>
          <Button onClick={() => setAddOpen(true)}>Tambah SOP Pertama</Button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {sops.map((s) => (
            <Card key={s.id} className="py-0">
              <CardContent className="flex flex-col gap-3 p-4">
                <div className="flex items-start gap-3">
                  <div className="flex min-w-0 flex-1 flex-col gap-1">
                    <span className="font-medium">{s.title}</span>
                    {s.body && (
                      <span className="text-muted-foreground line-clamp-2 text-xs">
                        {s.body}
                      </span>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setEditSop(s)}
                    >
                      <Pencil className="size-4" />
                      <span className="sr-only">Edit SOP</span>
                    </Button>
                    <AlertDialog>
                      <AlertDialogTrigger
                        render={<Button variant="ghost" size="icon" />}
                      >
                        <Trash2 className="size-4" />
                        <span className="sr-only">Hapus SOP</span>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Hapus SOP?</AlertDialogTitle>
                          <AlertDialogDescription>
                            SOP &quot;{s.title}&quot; akan dihapus dari
                            knowledge base. Chatbot tidak lagi memakainya
                            untuk rekomendasi.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Batal</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={async () => {
                              try {
                                await deleteSop(s.id);
                                toast.success("SOP dihapus.");
                              } catch (err) {
                                toast.error(
                                  err instanceof Error
                                    ? err.message
                                    : "Gagal menghapus SOP.",
                                );
                              }
                            }}
                          >
                            Hapus
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-muted-foreground text-sm">
                    {s.steps.length} langkah
                  </span>
                  {s.reference && (
                    <span className="text-muted-foreground truncate text-xs">
                      · {s.reference}
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <SopFormDialog open={addOpen} onOpenChange={setAddOpen} onSaved={() => {}} />
      <SopFormDialog
        open={editSop !== undefined}
        onOpenChange={(o) => {
          if (!o) setEditSop(undefined);
        }}
        sop={editSop}
        onSaved={() => {}}
      />
    </div>
  );
}
```

- [ ] **Step 3: Verify no remaining references to `SopMode`/`SOP_MODE_LABEL` anywhere**

Run: `grep -rln "SopMode\|SOP_MODE_LABEL" frontend/src`
Expected: no output.

- [ ] **Step 4: Run typecheck, lint, build, and the full test suite**

Run: `cd frontend && bunx tsc --noEmit`
Expected: no errors.
Run: `cd frontend && bun run lint`
Expected: no errors.
Run: `cd frontend && bun run build`
Expected: succeeds, all routes generated.
Run: `cd frontend && bun run test`
Expected: all suites pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/sop-form-dialog.tsx "frontend/src/app/(app)/sop/page.tsx"
git commit -m "feat(frontend): update SOP UI — drop failure-mode taxonomy, use real backend"
```

---

### Task 8: Verification

**Files:** none (verification only).

- [ ] **Step 1: Full frontend gate**

Run: `cd frontend && bunx tsc --noEmit && bun run lint && bun run build && bun run test`
Expected: all four pass. This is the same gate used in every prior sub-project.

- [ ] **Step 2: Backend static verification**

Run (from the repo root):
```bash
python3 -c "
import ast
for f in [
    'backend/app/schemas/machine.py',
    'backend/app/api/routes_machine.py',
    'backend/app/db/migrations/versions/0010_sop_library.py',
    'backend/app/db/models.py',
    'backend/app/schemas/sop.py',
    'backend/app/api/routes_sop.py',
    'backend/app/main.py',
]:
    ast.parse(open(f).read())
    print(f, 'OK')
"
```
Expected: all seven files print `OK`.

- [ ] **Step 3: If a real Docker + `.env` environment is available, run live verification**

```bash
docker compose -f compose.yaml -f dev.compose.yaml up -d --build postgres backend
docker compose -f compose.yaml -f dev.compose.yaml exec backend alembic upgrade head
```
Expected: migration `0010` applies without error. Then, with a valid `engineer`+ JWT (`POST /auth/login`):
```bash
curl -s -X POST http://localhost:8002/machines -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"name":"Test Machine","machine_type":"Haas"}'
curl -s -X PATCH http://localhost:8002/machines/$MACHINE_ID -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"name":"Renamed"}'
curl -s -X DELETE http://localhost:8002/machines/$MACHINE_ID -H "Authorization: Bearer $TOKEN" -w "\n%{http_code}\n"
curl -s -X POST http://localhost:8002/sops -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"title":"Test SOP","steps":[]}'
curl -s http://localhost:8002/sops
```
Expected: create/update/delete all succeed (delete returns `204`), `GET /sops` returns the created SOP without needing a token.

If Docker/`.env` isn't available in your environment, report that plainly (same category of environment limitation already noted in the two prior sub-projects' plans) rather than skipping silently — Steps 1-2 remain the required minimum bar for this task.

- [ ] **Step 4: Report findings**

No commit for this task (verification only) — report the results from Steps 1-3 in your task report.
