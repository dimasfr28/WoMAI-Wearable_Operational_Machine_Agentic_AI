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
