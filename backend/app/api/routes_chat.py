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

from app.api.routes_report import RAW_FEATURE_COLS, _historical_df, _run_report_pipeline
from app.api.routes_report import get_latest_report as _get_latest_report
from app.api.routes_sensor import _bump_failure_count_if_needed, assign_run_id
from app.db.models import ChatMessage, ChatSession, Machine, Prediction, SensorReading, SensorRun, Sop, User
from app.db.session import SessionLocal
from app.llm.groq_client import chat, chat_json
from app.ml.predictor_clasification import RAW_TO_MODEL_COL, ClasificationResult, predict_failure
from app.ml.shap_tool import explain_failure_shap
from app.notifications.telegram import notify_new_reading
from app.rag.final_report import WhatIfContext, generate_what_if_narrative
from app.schemas.chat import ChatIn
from app.schemas.sensor import SensorReadingIn

router = APIRouter(tags=["chat"])

SYSTEM_PROMPT_INTENT = """Kamu adalah pengklasifikasi intent untuk asisten pemeliharaan prediktif mesin CNC Haas.
Baca pesan user dan balas HANYA JSON dengan skema persis ini (tanpa teks lain):
{{
  "intent": "predict" | "latest_report" | "sop_lookup" | "what_if" | "chitchat",
  "machine_id": "<uuid dari daftar mesin di bawah, atau null>",
  "air_temperature_k": <angka atau null>,
  "process_temperature_k": <angka atau null>,
  "rotational_speed_rpm": <angka atau null>,
  "tool_wear_min": <angka atau null>,
  "sop_query": "<ringkasan gejala/pertanyaan user, atau null>"
}}

Aturan:
- "predict": user menyebutkan kondisi/nilai sensor mesin dan ingin tahu apakah mesin akan gagal — data ini akan DISIMPAN sebagai pembacaan sensor sungguhan.
- "latest_report": user menanyakan laporan/prediksi/status terakhir suatu mesin.
- "sop_lookup": user menanyakan cara menangani suatu gejala/masalah, TANPA menyebut nilai sensor baru.
- "what_if": user bertanya "bagaimana jika" / "seandainya" suatu nilai sensor diubah — simulasi HIPOTETIS, TIDAK disimpan sebagai data sungguhan. User boleh menyebut hanya SEBAGIAN nilai sensor (sisanya memakai data sungguhan terakhir mesin itu).
- "chitchat": sapaan atau pertanyaan umum yang tidak cocok kategori di atas.
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


def _resolve_session_uuid(user: User, session_id: str) -> uuid_module.UUID:
    """UUID sesi diturunkan dari (user, session_id) bersama-sama -- BUKAN dari
    session_id saja -- supaya dua user berbeda yang kebetulan mengirim
    session_id sama (mis. fallback "default" di frontend) tidak akan pernah
    tabrakan pada UUID yang sama. session_id valid UUID pun tetap digabung
    dengan identitas user, konsisten dan dapat diprediksi untuk user yang
    sama di setiap panggilan (kontinuitas terjaga tanpa perlu deteksi
    tabrakan/mint UUID acak yang tidak persisten)."""
    return uuid_module.uuid5(uuid_module.NAMESPACE_URL, f"{user.id}:{session_id}")


def _get_or_create_session(db: Session, user: User, session_id: str) -> ChatSession:
    session_uuid = _resolve_session_uuid(user, session_id)
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_uuid, ChatSession.user_id == user.id)
        .first()
    )
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

    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    notify_new_reading(machine.name if machine else "Unknown Machine", pred_result)

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


def _hypothetical_prediction_event_data(result: ClasificationResult) -> dict:
    return {
        "label": result.label,
        "probability": result.probability,
        "healthScore": round((1 - result.probability) * 100, 2),
        "riskLevel": _risk_level(result.probability),
    }


def _shap_dict_to_event_data(shap_result: dict) -> dict:
    return {
        "contributions": [
            {"feature": f["feature_name"], "value": f["shap_value"]} for f in shap_result["features"]
        ],
    }


def _run_what_if(db: Session, intent_data: dict):
    """Simulasi hipotetis: TIDAK menulis ke sensor_readings/sensor_runs/predictions
    (lihat WhatIfContext di app/rag/final_report.py) -- predict_failure()+
    explain_failure_shap() dipanggil murni in-memory, supaya data simulasi tidak
    pernah tercampur dengan data sensor sungguhan (termasuk feed ESP32 nanti)."""
    machine_id = intent_data.get("machine_id")
    if not machine_id:
        yield {"type": "needs_input", "message": "Mesin mana yang mau disimulasikan?"}
        return

    yield {"type": "status", "message": "Menjalankan simulasi what-if..."}

    baseline_reading = (
        db.query(SensorReading)
        .join(SensorRun, SensorRun.id == SensorReading.run_id)
        .filter(SensorRun.machine_id == machine_id)
        .order_by(SensorReading.reading_timestamp.desc())
        .first()
    )

    baseline_feature_row: dict | None = None
    if baseline_reading is not None:
        baseline_feature_row = {
            "air_temperature_k": float(baseline_reading.air_temperature_k),
            "process_temperature_k": float(baseline_reading.process_temperature_k),
            "rotational_speed_rpm": int(baseline_reading.rotational_speed_rpm),
            "tool_wear_min": float(baseline_reading.tool_wear_min),
        }

    hypothetical_feature_row: dict = dict(baseline_feature_row) if baseline_feature_row else {}
    changed_features: dict[str, float] = {}
    for raw_key in RAW_FEATURE_COLS:
        if intent_data.get(raw_key) is not None:
            hypothetical_feature_row[raw_key] = intent_data[raw_key]
            changed_features[RAW_TO_MODEL_COL[raw_key]] = intent_data[raw_key]

    missing = [f for f in RAW_FEATURE_COLS if hypothetical_feature_row.get(f) is None]
    if missing:
        labels = ", ".join(MISSING_FIELD_LABEL[f] for f in missing)
        yield {
            "type": "needs_input",
            "message": (
                f"Belum ada data sensor tersimpan untuk mesin ini, jadi sebutkan {labels} "
                "supaya saya bisa simulasikan."
            ),
        }
        return

    hypothetical_result = predict_failure(hypothetical_feature_row)

    historical_df = _historical_df(db, machine_id)
    if len(historical_df) >= 5:
        shap_result = explain_failure_shap(hypothetical_feature_row, historical_df)
    else:
        shap_result = {
            "base_value": hypothetical_result.probability,
            "features": [
                {
                    "feature_name": RAW_TO_MODEL_COL[f],
                    "value": hypothetical_feature_row[f],
                    "shap_value": 0.0,
                    "rank": i + 1,
                }
                for i, f in enumerate(RAW_FEATURE_COLS)
            ],
        }

    baseline_prediction: Prediction | None = None
    if baseline_reading is not None:
        baseline_prediction = (
            db.query(Prediction)
            .filter(Prediction.sensor_reading_id == baseline_reading.id)
            .order_by(Prediction.created_at.desc())
            .first()
        )

    yield {"type": "prediction", "data": _hypothetical_prediction_event_data(hypothetical_result)}
    yield {"type": "shap", "data": _shap_dict_to_event_data(shap_result)}

    machine_row = db.query(Machine).filter(Machine.id == machine_id).first()
    top_feature_name = shap_result["features"][0]["feature_name"] if shap_result["features"] else "?"
    narrative = generate_what_if_narrative(
        WhatIfContext(
            machine_name=machine_row.name if machine_row else "mesin ini",
            hypothetical_label=hypothetical_result.label,
            hypothetical_probability=hypothetical_result.probability,
            baseline_label=baseline_prediction.predicted_label if baseline_prediction else None,
            baseline_probability=(
                float(baseline_prediction.failure_probability) if baseline_prediction else None
            ),
            top_feature_name=top_feature_name,
            changed_features=changed_features,
        )
    )
    yield {"type": "text", "delta": narrative}


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

            # rancangan.txt Section 8: mesin aktif dipilih SEBELUM masuk chat
            # (frontend kirim payload.machine_id dari state global), jadi
            # TIDAK perlu lagi diekstrak dari teks pesan atau ditanyakan lewat
            # needs_input — payload.machine_id selalu menang atas hasil
            # _classify_intent's LLM-guessed machine_id ketika ada.
            if payload.machine_id:
                intent_data["machine_id"] = payload.machine_id

            if intent == "predict":
                generator = _run_predict(db, user, intent_data, sops)
            elif intent == "latest_report":
                generator = _run_latest_report(db, intent_data, sops)
            elif intent == "what_if":
                generator = _run_what_if(db, intent_data)
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
