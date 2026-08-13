# Backend Chat Agent (`/chat`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real backend `POST /chat` endpoint (SSE) that reuses the existing predict/SHAP/CRAG/report pipeline as an "agent with tools", replacing the fully-mocked chat feature in the Next.js frontend — this is the highest-priority gap before the AIC COMPFEST 18 penyisihan deadline (25 Agustus 2026).

**Architecture:** A router-style intent classifier (one `chat_json()` call) extracts `intent` + parameters from the user's message, then dispatches to one of three handlers (`predict`, `latest_report`, `sop_lookup`) or a `chitchat` fallback. `predict` inserts a real `SensorRun`/`SensorReading` and calls the exact same `_run_report_pipeline()` function already used by `POST /sensor/readings` — no reimplementation of SHAP/CRAG/report logic. All handlers are Python generators yielding SSE-ready event dicts; the endpoint streams them and persists the full turn to `chat_sessions`/`chat_messages` (existing, previously-unused tables).

**Tech Stack:** FastAPI (`StreamingResponse`), SQLAlchemy, Groq (`chat`/`chat_json`, already in the codebase), existing `predict_failure`/`explain_failure_shap`/`run_crag`/`_run_report_pipeline` modules.

## Global Constraints

- The frontend (`frontend/src/app/api/chat/route.ts`, already committed, NOT modified by this plan) POSTs `{"message": str, "session_id": str}` to `${BACKEND_URL}/chat` and expects an SSE stream of lines `data: {json}\n\n`, where each JSON object has one of these shapes: `{"type": "status", "message": str}`, `{"type": "prediction", "data": {...}}`, `{"type": "shap", "data": {...}}`, `{"type": "sop", "data": {...}}`, `{"type": "text", "delta": str}`, `{"type": "needs_input", "message": str}`, `{"type": "error", "message": str}`. The route path is exactly `/chat` with **no prefix segment** (not `/chat/message` or similar).
- `prediction` event data shape: `{"label": bool, "probability": float, "healthScore": float, "riskLevel": "rendah"|"sedang"|"tinggi"}`. `riskLevel` thresholds: `probability < 0.3` → `"rendah"`, `< 0.6` → `"sedang"`, else `"tinggi"`.
- `shap` event data shape: `{"contributions": [{"feature": str, "value": float}, ...]}`.
- `sop` event data shape: `{"title": str, "steps": [{"id": str, "text": str, "priority": "segera"|"terjadwal", "estimatedMinutes": int}, ...]}`.
- `downtime` event is **never emitted** by this plan — no code in this plan produces it.
- **Critical technical constraint**: the endpoint's DB session for work done *inside* the SSE generator must be created directly via `SessionLocal()` (`from app.db.session import SessionLocal`), **not** via `Depends(get_db)`. FastAPI tears down `Depends(get_db)`-yielded sessions as soon as the endpoint function returns the `StreamingResponse` object — before the generator body (which runs during actual streaming) executes any queries. Using `Depends(get_db)` for generator-body DB work will fail with a closed-session error partway through the first real request.
- Auth: `POST /chat` requires `Depends(get_current_user)` (any logged-in user, no role restriction) — matches the pattern in `backend/app/api/routes_machine.py:29`.
- `ChatSession.id`/`ChatMessage.session_id` are `UUID` columns. The frontend normally sends a real UUID (`crypto.randomUUID()`, `frontend/src/app/(app)/chat/page.tsx:7`) but has a non-UUID fallback literal `"default"` (`frontend/src/app/api/chat/route.ts:37`) that must not crash the backend — resolve any non-UUID `session_id` string to a deterministic UUID via `uuid.uuid5(uuid.NAMESPACE_URL, session_id)` rather than raising an error.
- Reuse, never reimplement: `assign_run_id()`/`_bump_failure_count_if_needed()` (`backend/app/api/routes_sensor.py`), `_run_report_pipeline()` (`backend/app/api/routes_report.py`), `get_latest_report()` (`backend/app/api/routes_report.py`), `predict_failure()` (`backend/app/ml/predictor.py`). Import and call them directly as plain Python functions.
- Commit messages in this repo don't follow a strict prefix convention seen elsewhere in this plan's tasks, but AIC's rubric explicitly grades commit-message quality via Conventional Commits (`feat:`/`fix:`/`refactor:`) — every commit in this plan MUST use one of those prefixes.

---

### Task 1: Backend — `/chat` endpoint skeleton, intent classification, chitchat + needs_input paths

**Files:**
- Create: `backend/app/schemas/chat.py`
- Create: `backend/app/api/routes_chat.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Produces: `POST /chat` (SSE), registered in `main.py`. Internal generator functions with this shared signature convention — each yields `dict` event objects (not yet SSE-encoded): `_run_predict(db, user, intent_data, sops) -> Iterator[dict]`, `_run_latest_report(db, intent_data, sops) -> Iterator[dict]`, `_run_sop_lookup(intent_data, sops) -> Iterator[dict]`, `_run_chitchat(message) -> Iterator[dict]`. Task 2 and Task 3 will replace the placeholder bodies of `_run_predict`/`_run_latest_report`/`_run_sop_lookup` — their signatures and the two `needs_input` checks inside `_run_predict` must not change.
- Consumes: `chat`/`chat_json` from `backend/app/llm/groq_client.py` (existing, signatures: `chat(messages: list[dict], model=None, temperature=0.2) -> str`, `chat_json(messages: list[dict], model=None) -> str`), `get_current_user` from `backend/app/api/deps.py`, `SessionLocal` from `backend/app/db/session.py`, `ChatSession`/`ChatMessage`/`Machine`/`Sop`/`User` from `backend/app/db/models.py`.

- [ ] **Step 1: Create the request schema**

Create `backend/app/schemas/chat.py`:
```python
from pydantic import BaseModel


class ChatIn(BaseModel):
    message: str
    session_id: str
```

- [ ] **Step 2: Create `routes_chat.py` with session/message persistence helpers and intent classification**

Create `backend/app/api/routes_chat.py`:
```python
"""POST /chat — chat agent endpoint. Router intent sederhana (satu panggilan
chat_json() mengekstrak intent+parameter dari pesan user), BUKAN native
tool-calling Groq (groq_client.py belum dukung `tools=`) — lebih deterministik
untuk demo dalam waktu terbatas. Dispatch ke predict/latest_report/sop_lookup
(reuse pipeline yang sudah ada, TIDAK reimplementasi SHAP/CRAG/report) atau
chitchat. Respons SSE mengikuti kontrak yang sudah diharapkan
frontend/src/app/api/chat/route.ts.

PENTING: db session untuk kerja di dalam generator dibuat baru lewat
SessionLocal() langsung (BUKAN lewat Depends(get_db)) -- FastAPI menutup
session dependency segera setelah endpoint function return StreamingResponse,
sebelum generator body-nya benar-benar dieksekusi saat streaming berjalan.
Pakai Depends(get_db) di sini akan menyebabkan error "session closed" di
tengah stream pada request sungguhan pertama.
"""
from __future__ import annotations

import json
import uuid as uuid_module

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import ChatMessage, ChatSession, Machine, Sop, User
from app.db.session import SessionLocal
from app.llm.groq_client import chat, chat_json
from app.schemas.chat import ChatIn

router = APIRouter(tags=["chat"])

SYSTEM_PROMPT_INTENT = """Kamu adalah pengklasifikasi intent untuk asisten pemeliharaan prediktif mesin CNC Haas.
Baca pesan user dan balas HANYA JSON dengan skema persis ini (tanpa teks lain):
{{
  "intent": "predict" | "latest_report" | "sop_lookup" | "chitchat",
  "machine_id": "<uuid dari daftar mesin di bawah, atau null>",
  "air_temperature_k": <angka atau null>,
  "process_temperature_k": <angka atau null>,
  "rotational_speed_rpm": <angka atau null>,
  "tool_wear_min": <angka atau null>,
  "sop_query": "<ringkasan gejala/pertanyaan user, atau null>"
}}

Aturan:
- "predict": user menyebutkan kondisi/nilai sensor mesin dan ingin tahu apakah mesin akan gagal.
- "latest_report": user menanyakan laporan/prediksi/status terakhir suatu mesin.
- "sop_lookup": user menanyakan cara menangani suatu gejala/masalah, TANPA menyebut nilai sensor baru.
- "chitchat": sapaan atau pertanyaan umum yang tidak cocok tiga kategori di atas.
- machine_id HARUS salah satu dari daftar di bawah (cocokkan nama mesin yang disebut user), atau null kalau tidak disebut/tidak cocok.
- Field sensor: HANYA isi kalau user menyebutkan angkanya secara eksplisit di pesan ini. Jangan menebak.

Daftar mesin yang ada:
{machines}
"""

MISSING_FIELD_LABEL = {
    "air_temperature_k": "suhu udara (K)",
    "process_temperature_k": "suhu proses (K)",
    "rotational_speed_rpm": "kecepatan putaran (RPM)",
    "tool_wear_min": "keausan tool (menit)",
}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _resolve_session_uuid(session_id: str) -> uuid_module.UUID:
    try:
        return uuid_module.UUID(session_id)
    except ValueError:
        return uuid_module.uuid5(uuid_module.NAMESPACE_URL, session_id)


def _get_or_create_session(db: Session, user: User, session_id: str) -> ChatSession:
    session_uuid = _resolve_session_uuid(session_id)
    session = db.query(ChatSession).filter(ChatSession.id == session_uuid).first()
    if session is not None:
        return session
    session = ChatSession(id=session_uuid, user_id=user.id, title="Chat baru")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _save_message(db: Session, session: ChatSession, role: str, content: str) -> None:
    db.add(ChatMessage(session_id=session.id, role=role, content=content))
    db.commit()


def _classify_intent(message: str, machines: list[Machine]) -> dict:
    machine_list = "\n".join(f"- {m.id}: {m.name}" for m in machines) or "(belum ada mesin terdaftar)"
    system = SYSTEM_PROMPT_INTENT.format(machines=machine_list)
    raw = chat_json(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ]
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    return {
        "intent": data.get("intent") or "chitchat",
        "machine_id": data.get("machine_id"),
        "air_temperature_k": data.get("air_temperature_k"),
        "process_temperature_k": data.get("process_temperature_k"),
        "rotational_speed_rpm": data.get("rotational_speed_rpm"),
        "tool_wear_min": data.get("tool_wear_min"),
        "sop_query": data.get("sop_query"),
    }


def _missing_sensor_fields(intent_data: dict) -> list[str]:
    return [f for f in MISSING_FIELD_LABEL if intent_data.get(f) is None]


def _run_predict(db: Session, user: User, intent_data: dict, sops: list[Sop]):
    missing = _missing_sensor_fields(intent_data)
    if missing:
        labels = ", ".join(MISSING_FIELD_LABEL[f] for f in missing)
        yield {"type": "needs_input", "message": f"Sebutkan juga {labels} supaya saya bisa jalankan prediksi."}
        return
    if not intent_data.get("machine_id"):
        yield {"type": "needs_input", "message": "Mesin mana yang dimaksud? Sebutkan nama mesinnya."}
        return
    # TODO(Task 2): jalankan prediksi sungguhan (insert SensorRun/SensorReading,
    # panggil _run_report_pipeline, emit prediction/shap/sop/text).
    yield {"type": "text", "delta": "Fitur prediksi sedang dalam pengembangan."}


def _run_latest_report(db: Session, intent_data: dict, sops: list[Sop]):
    if not intent_data.get("machine_id"):
        yield {"type": "needs_input", "message": "Mesin mana yang laporannya ingin dilihat?"}
        return
    # TODO(Task 3): ambil laporan sungguhan (reuse get_latest_report()).
    yield {"type": "text", "delta": "Fitur laporan terakhir sedang dalam pengembangan."}


def _run_sop_lookup(intent_data: dict, sops: list[Sop]):
    # TODO(Task 3): cari SOP sungguhan (match_sop()).
    yield {"type": "text", "delta": "Fitur pencarian SOP sedang dalam pengembangan."}


def _run_chitchat(message: str):
    reply = chat(
        [
            {
                "role": "system",
                "content": "Kamu adalah asisten pemeliharaan prediktif mesin CNC Haas. Jawab singkat, ramah, dalam Bahasa Indonesia.",
            },
            {"role": "user", "content": message},
        ]
    )
    for word in reply.split():
        yield {"type": "text", "delta": word + " "}


@router.post("/chat")
def chat_endpoint(payload: ChatIn, user: User = Depends(get_current_user)):
    def event_stream():
        db = SessionLocal()
        final_text_parts: list[str] = []
        try:
            session = _get_or_create_session(db, user, payload.session_id)
            _save_message(db, session, "user", payload.message)

            machines = db.query(Machine).order_by(Machine.created_at.asc()).all()
            sops = db.query(Sop).order_by(Sop.created_at.asc()).all()
            intent_data = _classify_intent(payload.message, machines)
            intent = intent_data["intent"]

            if intent == "predict":
                generator = _run_predict(db, user, intent_data, sops)
            elif intent == "latest_report":
                generator = _run_latest_report(db, intent_data, sops)
            elif intent == "sop_lookup":
                generator = _run_sop_lookup(intent_data, sops)
            else:
                generator = _run_chitchat(payload.message)

            for event in generator:
                yield _sse(event)
                if event["type"] in ("text", "needs_input"):
                    final_text_parts.append(event.get("delta") or event.get("message") or "")

            _save_message(db, session, "assistant", "".join(final_text_parts).strip())
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": f"Terjadi kesalahan: {exc}"})
        finally:
            db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

- [ ] **Step 3: Register the router**

In `backend/app/main.py`, find:
```python
from app.api.routes_auth import router as auth_router
from app.api.routes_knowledgebase import router as knowledgebase_router
from app.api.routes_machine import router as machine_router
from app.api.routes_report import router as report_router
from app.api.routes_sensor import router as sensor_router
from app.api.routes_sop import router as sop_router
```
Replace with:
```python
from app.api.routes_auth import router as auth_router
from app.api.routes_chat import router as chat_router
from app.api.routes_knowledgebase import router as knowledgebase_router
from app.api.routes_machine import router as machine_router
from app.api.routes_report import router as report_router
from app.api.routes_sensor import router as sensor_router
from app.api.routes_sop import router as sop_router
```
Find:
```python
app.include_router(auth_router)
app.include_router(machine_router)
app.include_router(knowledgebase_router)
app.include_router(sensor_router)
app.include_router(report_router)
app.include_router(sop_router)
```
Replace with:
```python
app.include_router(auth_router)
app.include_router(machine_router)
app.include_router(knowledgebase_router)
app.include_router(sensor_router)
app.include_router(report_router)
app.include_router(sop_router)
app.include_router(chat_router)
```

- [ ] **Step 4: Verify it parses and imports cleanly**

Run from repo root:
```bash
python3 -c "
import ast
for f in ['backend/app/schemas/chat.py', 'backend/app/api/routes_chat.py', 'backend/app/main.py']:
    ast.parse(open(f).read())
    print(f, 'OK')
"
```
Expected: all three print `OK`.

If a real Docker + `.env` environment is available, additionally verify live:
```bash
docker compose -f compose.yaml -f dev.compose.yaml up -d --build backend
# with a valid JWT from POST /auth/login:
curl -N -X POST http://localhost:8002/chat -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"halo","session_id":"11111111-1111-1111-1111-111111111111"}'
```
Expected: SSE lines with `"type":"text"` events forming a greeting reply, no server error. Also test an incomplete predict message, e.g. `{"message":"mesin saya suhu prosesnya 320K","session_id":"..."}"` → expect a `"type":"needs_input"` event asking for the other missing fields.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/chat.py backend/app/api/routes_chat.py backend/app/main.py
git commit -m "feat(backend): add /chat endpoint skeleton with intent classification and chitchat"
```

---

### Task 2: Backend — `predict` intent (full pipeline reuse) + SOP matching

**Files:**
- Modify: `backend/app/api/routes_chat.py`

**Interfaces:**
- Consumes: `assign_run_id`, `_bump_failure_count_if_needed` from `backend/app/api/routes_sensor.py`; `_run_report_pipeline` from `backend/app/api/routes_report.py`; `predict_failure` from `backend/app/ml/predictor.py`; `SensorReadingIn` from `backend/app/schemas/sensor.py`; `SensorReading` from `backend/app/db/models.py`.
- Produces: `match_sop(query: str, sops: list[Sop]) -> Sop | None` — reused by Task 3's `_run_sop_lookup`. `_prediction_to_event_data(prediction) -> dict`, `_shap_to_event_data(shap) -> dict`, `_sop_to_event_data(sop: Sop) -> dict` — reused by Task 3's `_run_latest_report`.

- [ ] **Step 1: Add new imports**

In `backend/app/api/routes_chat.py`, find:
```python
from __future__ import annotations

import json
import uuid as uuid_module

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import ChatMessage, ChatSession, Machine, Sop, User
from app.db.session import SessionLocal
from app.llm.groq_client import chat, chat_json
from app.schemas.chat import ChatIn
```
Replace with:
```python
from __future__ import annotations

import json
import uuid as uuid_module
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes_report import _run_report_pipeline
from app.api.routes_sensor import _bump_failure_count_if_needed, assign_run_id
from app.db.models import ChatMessage, ChatSession, Machine, SensorReading, Sop, User
from app.db.session import SessionLocal
from app.llm.groq_client import chat, chat_json
from app.ml.predictor import predict_failure
from app.schemas.chat import ChatIn
from app.schemas.sensor import SensorReadingIn
```

- [ ] **Step 2: Add risk-level, event-mapping, and SOP-matching helpers**

In `backend/app/api/routes_chat.py`, find:
```python
def _missing_sensor_fields(intent_data: dict) -> list[str]:
    return [f for f in MISSING_FIELD_LABEL if intent_data.get(f) is None]
```
Replace with:
```python
def _missing_sensor_fields(intent_data: dict) -> list[str]:
    return [f for f in MISSING_FIELD_LABEL if intent_data.get(f) is None]


def _risk_level(probability: float) -> str:
    if probability < 0.3:
        return "rendah"
    if probability < 0.6:
        return "sedang"
    return "tinggi"


def _prediction_to_event_data(prediction) -> dict:
    return {
        "label": prediction.predicted_label,
        "probability": prediction.failure_probability,
        "healthScore": prediction.health_score,
        "riskLevel": _risk_level(prediction.failure_probability),
    }


def _shap_to_event_data(shap) -> dict:
    return {
        "contributions": [
            {"feature": f.feature_name, "value": f.shap_value} for f in shap.features
        ],
    }


def _sop_to_event_data(sop: Sop) -> dict:
    return {
        "title": sop.title,
        "steps": [
            {
                "id": step["id"],
                "text": step["text"],
                "priority": step["priority"],
                "estimatedMinutes": step["estimated_minutes"],
            }
            for step in sop.steps
        ],
    }


def match_sop(query: str, sops: list[Sop]) -> Sop | None:
    """Dipakai oleh cabang predict/latest_report (query dari CRAG) maupun
    sop_lookup (query dari pesan user) -- satu mekanisme pencocokan SOP untuk
    semua tempat, bukan dua cara berbeda."""
    if not sops or not query:
        return None
    sop_list = "\n".join(f"- {s.id}: {s.title} (gejala: {s.symptoms})" for s in sops)
    system = (
        "Kamu memilih SOP paling relevan dari daftar berikut untuk menjawab "
        "pertanyaan/gejala user. Balas HANYA JSON: "
        '{"sop_id": "<id dari daftar>"} atau {"sop_id": null} kalau tidak ada '
        f"yang cukup relevan.\n\nDaftar SOP:\n{sop_list}"
    )
    raw = chat_json(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": query},
        ]
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    sop_id = data.get("sop_id")
    if not sop_id:
        return None
    return next((s for s in sops if str(s.id) == str(sop_id)), None)
```

- [ ] **Step 3: Replace `_run_predict`'s stub tail with the real pipeline**

In `backend/app/api/routes_chat.py`, find:
```python
def _run_predict(db: Session, user: User, intent_data: dict, sops: list[Sop]):
    missing = _missing_sensor_fields(intent_data)
    if missing:
        labels = ", ".join(MISSING_FIELD_LABEL[f] for f in missing)
        yield {"type": "needs_input", "message": f"Sebutkan juga {labels} supaya saya bisa jalankan prediksi."}
        return
    if not intent_data.get("machine_id"):
        yield {"type": "needs_input", "message": "Mesin mana yang dimaksud? Sebutkan nama mesinnya."}
        return
    # TODO(Task 2): jalankan prediksi sungguhan (insert SensorRun/SensorReading,
    # panggil _run_report_pipeline, emit prediction/shap/sop/text).
    yield {"type": "text", "delta": "Fitur prediksi sedang dalam pengembangan."}
```
Replace with:
```python
def _run_predict(db: Session, user: User, intent_data: dict, sops: list[Sop]):
    missing = _missing_sensor_fields(intent_data)
    if missing:
        labels = ", ".join(MISSING_FIELD_LABEL[f] for f in missing)
        yield {"type": "needs_input", "message": f"Sebutkan juga {labels} supaya saya bisa jalankan prediksi."}
        return
    machine_id = intent_data.get("machine_id")
    if not machine_id:
        yield {"type": "needs_input", "message": "Mesin mana yang dimaksud? Sebutkan nama mesinnya."}
        return

    yield {"type": "status", "message": "Menjalankan prediksi..."}

    reading_in = SensorReadingIn(
        timestamp=datetime.now(timezone.utc),
        air_temperature_k=intent_data["air_temperature_k"],
        process_temperature_k=intent_data["process_temperature_k"],
        rotational_speed_rpm=intent_data["rotational_speed_rpm"],
        tool_wear_min=intent_data["tool_wear_min"],
    )
    run = assign_run_id(reading_in, db, machine_id)
    reading = SensorReading(
        run_id=run.id,
        reading_timestamp=reading_in.timestamp,
        air_temperature_k=reading_in.air_temperature_k,
        process_temperature_k=reading_in.process_temperature_k,
        rotational_speed_rpm=reading_in.rotational_speed_rpm,
        tool_wear_min=reading_in.tool_wear_min,
        machine_failure=None,
        input_source="chat",
        created_by=user.id,
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)

    feature_row = {
        "air_temperature_k": float(reading.air_temperature_k),
        "process_temperature_k": float(reading.process_temperature_k),
        "rotational_speed_rpm": reading.rotational_speed_rpm,
        "tool_wear_min": float(reading.tool_wear_min),
    }
    pred_result = predict_failure(feature_row)
    reading.machine_failure = pred_result.label
    db.commit()
    db.refresh(reading)
    _bump_failure_count_if_needed(db, run, pred_result.label)

    report = _run_report_pipeline(db, reading, pred_result, machine_id)

    yield {"type": "prediction", "data": _prediction_to_event_data(report.prediction)}
    yield {"type": "shap", "data": _shap_to_event_data(report.shap)}

    if report.prediction.predicted_label and report.root_cause is not None:
        matched = match_sop(report.root_cause.query, sops)
        if matched is not None:
            yield {"type": "sop", "data": _sop_to_event_data(matched)}

    yield {"type": "text", "delta": report.final_report_text}
```

- [ ] **Step 4: Verify**

```bash
python3 -c "import ast; ast.parse(open('backend/app/api/routes_chat.py').read()); print('OK')"
```
If Docker+`.env` available, live-test: send a chat message with all 4 sensor values + a real machine name (e.g. `"mesin CNC Mill suhu udara 300K suhu proses 320K rpm 1500 tool wear 180 menit"`) with a valid JWT. Expect SSE events `status` → `prediction` → `shap` → (`sop` if failure predicted) → `text`, and confirm via `docker compose exec postgres psql ...` or `GET /machines/{id}/status`-adjacent query that a new `sensor_readings` row was actually inserted for that machine.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes_chat.py
git commit -m "feat(backend): implement predict intent by reusing the existing report pipeline"
```

---

### Task 3: Backend — `latest_report` and `sop_lookup` intents

**Files:**
- Modify: `backend/app/api/routes_chat.py`

**Interfaces:**
- Consumes: `get_latest_report` from `backend/app/api/routes_report.py` (called directly as a plain function, not via HTTP — `Depends(get_db)` in its signature is overridden by passing `db` explicitly), `match_sop`/`_prediction_to_event_data`/`_shap_to_event_data`/`_sop_to_event_data` from Task 2.

- [ ] **Step 1: Import `get_latest_report`**

In `backend/app/api/routes_chat.py`, find:
```python
from app.api.routes_report import _run_report_pipeline
```
Replace with:
```python
from fastapi import HTTPException

from app.api.routes_report import _run_report_pipeline
from app.api.routes_report import get_latest_report as _get_latest_report
```

- [ ] **Step 2: Replace `_run_latest_report`'s stub**

Find:
```python
def _run_latest_report(db: Session, intent_data: dict, sops: list[Sop]):
    if not intent_data.get("machine_id"):
        yield {"type": "needs_input", "message": "Mesin mana yang laporannya ingin dilihat?"}
        return
    # TODO(Task 3): ambil laporan sungguhan (reuse get_latest_report()).
    yield {"type": "text", "delta": "Fitur laporan terakhir sedang dalam pengembangan."}
```
Replace with:
```python
def _run_latest_report(db: Session, intent_data: dict, sops: list[Sop]):
    machine_id = intent_data.get("machine_id")
    if not machine_id:
        yield {"type": "needs_input", "message": "Mesin mana yang laporannya ingin dilihat?"}
        return

    yield {"type": "status", "message": "Mengambil laporan terakhir..."}

    try:
        report = _get_latest_report(machine_id, db)
    except HTTPException as exc:
        yield {"type": "text", "delta": str(exc.detail)}
        return

    yield {"type": "prediction", "data": _prediction_to_event_data(report.prediction)}
    yield {"type": "shap", "data": _shap_to_event_data(report.shap)}

    if report.prediction.predicted_label and report.root_cause is not None:
        matched = match_sop(report.root_cause.query, sops)
        if matched is not None:
            yield {"type": "sop", "data": _sop_to_event_data(matched)}

    yield {"type": "text", "delta": report.final_report_text}
```

- [ ] **Step 3: Replace `_run_sop_lookup`'s stub**

Find:
```python
def _run_sop_lookup(intent_data: dict, sops: list[Sop]):
    # TODO(Task 3): cari SOP sungguhan (match_sop()).
    yield {"type": "text", "delta": "Fitur pencarian SOP sedang dalam pengembangan."}
```
Replace with:
```python
def _run_sop_lookup(intent_data: dict, sops: list[Sop]):
    query = intent_data.get("sop_query") or ""
    yield {"type": "status", "message": "Mencari SOP relevan..."}
    matched = match_sop(query, sops)
    if matched is None:
        yield {"type": "text", "delta": "Belum ada SOP yang cocok untuk itu di knowledge base."}
        return
    yield {"type": "sop", "data": _sop_to_event_data(matched)}
    yield {"type": "text", "delta": f"Berikut SOP yang relevan: {matched.title}."}
```

- [ ] **Step 4: Verify**

```bash
python3 -c "import ast; ast.parse(open('backend/app/api/routes_chat.py').read()); print('OK')"
```
If Docker+`.env` available: (a) send "lihat laporan terakhir mesin X" for a machine with prior report data → expect `prediction`+`shap`+`text` (and `sop` if last prediction was a failure); for a machine with no report yet → expect a `text` event with the "Belum ada data sensor..." message, no server error. (b) send "bagaimana cara menangani mesin yang overheat?" → expect a `sop` event if any seeded SOP's symptoms are relevant, or a graceful "belum ada SOP yang cocok" `text` otherwise.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes_chat.py
git commit -m "feat(backend): implement latest_report and sop_lookup chat intents"
```

---

### Task 4: Frontend — fix `PredictionResult` type (drop AI4I failure-mode taxonomy)

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/components/chat/prediction-card.tsx`
- Modify: `frontend/src/app/(app)/mesin/page.tsx`
- Modify: `frontend/src/app/(app)/riwayat/page.tsx`
- Modify: `frontend/src/lib/mock/scenarios.ts`

**Interfaces:**
- Produces: `PredictionResult { label: boolean; probability: number; healthScore: number; riskLevel: RiskLevel }` (replacing the old AI4I-taxonomy shape) — this is what the `/chat` backend built in Tasks 1-3 emits as the `prediction` event's `data`, and what `ChatSession.lastPrediction` (unchanged field name) now holds.

- [ ] **Step 1: Update the type definition**

In `frontend/src/lib/types.ts`, find:
```ts
export type FailureType = "TWF" | "HDF" | "PWF" | "OSF" | "RNF" | "NONE";
export type RiskLevel = "rendah" | "sedang" | "tinggi";

export interface PredictionResult {
  failureProbability: number; // 0..1
  failureType: FailureType;
  failureTypeLabel: string;
  riskLevel: RiskLevel;
}
```
Replace with:
```ts
export type RiskLevel = "rendah" | "sedang" | "tinggi";

export interface PredictionResult {
  label: boolean; // true = model memprediksi kegagalan
  probability: number; // 0..1, failure_probability dari backend
  healthScore: number; // 0..100, (1-probability)*100
  riskLevel: RiskLevel;
}
```

- [ ] **Step 2: Update `prediction-card.tsx`**

In `frontend/src/components/chat/prediction-card.tsx`, find:
```tsx
export function PredictionCard({ data }: { data: PredictionResult }) {
  const pct = Math.round(data.failureProbability * 100);
```
Replace with:
```tsx
export function PredictionCard({ data }: { data: PredictionResult }) {
  const pct = Math.round(data.probability * 100);
```
Then find:
```tsx
          <div className="text-sm font-medium">
            {data.failureTypeLabel}
            {data.failureType !== "NONE" && ` (${data.failureType})`}
          </div>
```
Replace with:
```tsx
          <div className="text-sm font-medium">
            {data.label ? "Berpotensi gagal" : "Normal"}
          </div>
```

- [ ] **Step 3: Update `mesin/page.tsx`**

In `frontend/src/app/(app)/mesin/page.tsx`, find:
```tsx
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
```
Replace with:
```tsx
                    {lastPrediction ? (
                      <Badge
                        className={cn(RISK_BADGE[lastPrediction.riskLevel])}
                      >
                        {lastPrediction.label
                          ? `Berpotensi gagal · risiko ${lastPrediction.riskLevel}`
                          : "Normal"}
                      </Badge>
                    ) : (
                      <Badge variant="secondary">Belum ada prediksi</Badge>
                    )}
```

- [ ] **Step 4: Update `riwayat/page.tsx`**

In `frontend/src/app/(app)/riwayat/page.tsx`, grep for `failureType` (it appears once, in a ternary reading `s.lastPrediction.failureType === "NONE"` alongside `s.lastPrediction.riskLevel` inside a `RISK_BADGE`-classed `<Badge>`, the same pattern as `mesin/page.tsx` before Step 3's edit). Apply the same transformation as Step 3: replace the `failureType === "NONE" ? "Normal" : \`${failureType} · risiko ${riskLevel}\`` ternary with `label ? \`Berpotensi gagal · risiko ${riskLevel}\` : "Normal"`, keeping the surrounding `<Badge className={cn(RISK_BADGE[s.lastPrediction.riskLevel])}>` wrapper unchanged.

- [ ] **Step 5: Update mock scenario fixtures**

In `frontend/src/lib/mock/scenarios.ts`, every scenario object's `prediction` field currently has the shape `{failureProbability, failureType, failureTypeLabel, riskLevel}`. For each one: rename `failureProbability` → `probability`; add `label: <true if the scenario represents a failure, i.e. its old failureType !== "NONE", else false>`; add `healthScore: Math.round((1 - probability) * 100 * 100) / 100` (2 decimal places, matching the backend's `round(..., 2)` convention); remove `failureType` and `failureTypeLabel` entirely. Keep `riskLevel` unchanged. Also remove the `FailureType` import/usage from this file if it's imported solely for these fixtures (check `import type { ... } from "@/lib/types"` at the top of the file — `FailureType` no longer exists as an exported type after Step 1, so any import of it here must be deleted or it will fail to compile).

- [ ] **Step 6: Verify**

```bash
cd frontend && bunx tsc --noEmit && bun run lint && bun run build && bun run test
```
Expected: all four pass, no remaining references to `failureType`/`failureTypeLabel`/`FailureType` anywhere:
```bash
grep -rn "failureType\|FailureType" frontend/src
```
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/components/chat/prediction-card.tsx "frontend/src/app/(app)/mesin/page.tsx" "frontend/src/app/(app)/riwayat/page.tsx" frontend/src/lib/mock/scenarios.ts
git commit -m "fix(frontend): drop AI4I failure-mode taxonomy from PredictionResult, use real backend fields"
```

---

### Task 5: Verification

**Files:** none (verification only).

- [ ] **Step 1: Full frontend gate**

Run: `cd frontend && bunx tsc --noEmit && bun run lint && bun run build && bun run test`
Expected: all four pass.

- [ ] **Step 2: Backend static verification**

Run (from the repo root):
```bash
python3 -c "
import ast
for f in [
    'backend/app/schemas/chat.py',
    'backend/app/api/routes_chat.py',
    'backend/app/main.py',
]:
    ast.parse(open(f).read())
    print(f, 'OK')
"
```
Expected: all three print `OK`.

- [ ] **Step 3: Live verification (if Docker + real `.env` available)**

```bash
docker compose -f compose.yaml -f dev.compose.yaml up -d --build postgres backend
docker compose -f compose.yaml -f dev.compose.yaml exec backend alembic upgrade head
```
With a valid `engineer`+ JWT (`POST /auth/login`) and at least one machine + one SOP already seeded (create via `POST /machines`/`POST /sops` if needed):
```bash
curl -N -X POST http://localhost:8002/chat -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"halo","session_id":"11111111-1111-1111-1111-111111111111"}'
curl -N -X POST http://localhost:8002/chat -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"mesin <nama mesin nyata> suhu udara 300K suhu proses 320K rpm 1500 tool wear 180 menit","session_id":"11111111-1111-1111-1111-111111111111"}'
curl -N -X POST http://localhost:8002/chat -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"lihat laporan terakhir mesin <nama mesin nyata>","session_id":"11111111-1111-1111-1111-111111111111"}'
curl -N -X POST http://localhost:8002/chat -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"bagaimana cara menangani mesin overheat?","session_id":"11111111-1111-1111-1111-111111111111"}'
```
Expected: each returns a well-formed SSE stream ending cleanly (no exceptions in `docker compose logs backend`), with events matching the scenario as described in Tasks 1-3's own verify steps. Confirm via `docker compose exec postgres psql -U comfest -d comfest_db -c "SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT 10;"` that both user and assistant turns were persisted.

If Docker/`.env` isn't available, report that plainly rather than skipping silently — Steps 1-2 remain the required minimum bar.

- [ ] **Step 4: Manual E2E in the browser (if live environment available)**

Open `/chat`, send a message describing a machine condition, confirm the response comes from the real backend (check `docker compose logs backend` shows an incoming `POST /chat` request) rather than the mock fallback (`mockStream()` only triggers on a fetch failure/timeout, so a successful real response confirms the wiring end-to-end).

- [ ] **Step 5: Report findings**

No commit for this task (verification only) — report the results from Steps 1-4.
