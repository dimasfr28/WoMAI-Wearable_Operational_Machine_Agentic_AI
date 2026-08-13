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
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from fastapi import HTTPException

from app.api.routes_report import _run_report_pipeline
from app.api.routes_report import get_latest_report as _get_latest_report
from app.api.routes_sensor import _bump_failure_count_if_needed, assign_run_id
from app.db.models import ChatMessage, ChatSession, Machine, SensorReading, Sop, User
from app.db.session import SessionLocal
from app.llm.groq_client import chat, chat_json
from app.ml.predictor import predict_failure
from app.schemas.chat import ChatIn
from app.schemas.sensor import SensorReadingIn

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


def _run_sop_lookup(intent_data: dict, sops: list[Sop]):
    query = intent_data.get("sop_query") or ""
    yield {"type": "status", "message": "Mencari SOP relevan..."}
    matched = match_sop(query, sops)
    if matched is None:
        yield {"type": "text", "delta": "Belum ada SOP yang cocok untuk itu di knowledge base."}
        return
    yield {"type": "sop", "data": _sop_to_event_data(matched)}
    yield {"type": "text", "delta": f"Berikut SOP yang relevan: {matched.title}."}


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
