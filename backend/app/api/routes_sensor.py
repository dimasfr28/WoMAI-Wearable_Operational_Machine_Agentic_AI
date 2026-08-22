"""Section 7: POST /sensor/readings, POST /sensor/readings/batch, GET /sensor/runs.

Not explicitly named in Section 2's file tree (which only lists routes_knowledgebase.py,
routes_report.py, routes_auth.py) but required by the Section 7 API contract table —
kept as its own module for clarity rather than overloading routes_report.py.
"""
from __future__ import annotations

import logging
import statistics

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.api.deps import get_current_user_optional, require_role
from app.api.routes_report import _run_report_pipeline
from app.config import settings
from app.db.models import Document, DocumentChunk, Machine, SensorReading, SensorRun, User
from app.db.session import get_db
from app.ingestion.chunking_sensor import ReadingLike, RunLike, build_run_chunk
from app.ingestion.embedder import embed_texts
from app.ml.outlier import RunIqrBounds, compute_run_iqr_bounds, is_value_outlier
from app.ml.predictor_clasification import predict_failure
from app.notifications.telegram import notify_new_reading
from app.schemas.sensor import (
    SensorHistoryOut,
    SensorHistoryPointOut,
    SensorParamStatsOut,
    SensorReadingBatchIn,
    SensorReadingIn,
    SensorReadingOut,
    SensorReadingSubmitResponseOut,
    SensorRunOut,
)
from app.vectorstore.chroma_client import (
    get_bot_sensor_collection,
    get_sensor_collection,
    upsert_chunks,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sensor", tags=["sensor"])


def _require_machine(db: Session, machine_id: str) -> Machine:
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    return machine


def _is_zero_reading(reading: SensorReadingIn) -> bool:
    """A raw value of exactly 0 on any of the 4 sensor channels indicates a
    disconnected/faulty sensor on the IoT (ESP32) side, not a real
    measurement — reject the whole reading rather than storing it."""
    return (
        reading.air_temperature_k == 0
        or reading.process_temperature_k == 0
        or reading.rotational_speed_rpm == 0
        or reading.tool_wear_min == 0
    )


# Headers Cloudflare (and cloudflared, for Tunnel) injects into every request
# it proxies — present only on requests that went through Cloudflare's edge,
# never on a request hitting this server directly (e.g. curl/Swagger UI
# against localhost:8002). Peer IP alone can't distinguish these inside
# Docker: both a genuine localhost request and a tunnel-forwarded one arrive
# via the same bridge-gateway address from this container's point of view.
_TUNNEL_HEADERS = ("cf-connecting-ip", "cf-ray", "cf-visitor")


def _require_direct_localhost_request(request: Request) -> None:
    """Rejects any request proxied through Cloudflare Tunnel — this endpoint
    is meant to accept data only from a direct local caller (Swagger UI at
    /docs, curl, etc. against localhost:8002). Simulated data never goes
    through this check at all: SimulationManager writes straight to the DB,
    it never calls this HTTP endpoint."""
    if any(h in request.headers for h in _TUNNEL_HEADERS):
        raise HTTPException(
            status_code=403,
            detail="This endpoint only accepts direct localhost requests, not requests proxied through a tunnel.",
        )


def _open_new_run(db: Session, machine_id: str, reading: SensorReadingIn) -> SensorRun:
    """Section 6.3 — buka run baru untuk `machine_id` tertentu. `failure_count`
    mulai dari 0 karena `machine_failure` untuk reading ini belum diketahui pada
    tahap ini (belum diprediksi) — akan di-increment setelah predict_failure()
    dipanggil di submit_reading()/submit_readings_batch(), lihat
    `_bump_failure_count_if_needed`. Run label dihitung per-mesin (bukan global)
    supaya "Run 1" konsisten muncul untuk setiap mesin baru, bukan angka global
    yang terus naik lintas mesin."""
    n = db.query(SensorRun).filter(SensorRun.machine_id == machine_id).count()
    run = SensorRun(
        machine_id=machine_id,
        run_label=f"Run {n + 1}",
        start_timestamp=reading.timestamp,
        end_timestamp=reading.timestamp,
        sample_count=1,
        failure_count=0,
        is_closed=False,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _close_run_and_build_chunk(db: Session, run: SensorRun) -> None:
    """Section 6.4: dipanggil setiap kali sebuah run ditutup, membangun knowledgebase
    chunk dari seluruh readings run tersebut dan menyimpannya ke Postgres + Chroma."""
    readings = (
        db.query(SensorReading)
        .filter(SensorReading.run_id == run.id)
        .order_by(SensorReading.reading_timestamp.asc())
        .all()
    )
    if not readings:
        return

    reading_likes = [
        ReadingLike(
            air_temperature_k=float(r.air_temperature_k),
            process_temperature_k=float(r.process_temperature_k),
            rotational_speed_rpm=int(r.rotational_speed_rpm),
            tool_wear_min=float(r.tool_wear_min),
            machine_failure=r.machine_failure,
        )
        for r in readings
    ]
    chunk = build_run_chunk(RunLike(run_label=run.run_label), reading_likes)

    document = Document(
        machine_id=run.machine_id,
        source_type="sensor_numeric",
        doc_name=chunk["doc"],
        machine_type=chunk["machine_type"],
        status="processing",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    db_chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        heading_1=chunk["heading_1"],
        heading_2=chunk["heading_2"],
        content=chunk["content"],
        chroma_id="",
    )
    db.add(db_chunk)
    db.flush()
    db_chunk.chroma_id = str(db_chunk.id)
    db.commit()

    try:
        embedding = embed_texts([db_chunk.content])[0]
        ids = [db_chunk.chroma_id]
        embeddings = [embedding]
        documents = [db_chunk.content]
        metadatas = [
            {
                "postgres_chunk_id": str(db_chunk.id),
                "document_id": str(document.id),
                "machine_id": str(document.machine_id) if document.machine_id else "",
                "doc": document.doc_name,
                "machine_type": document.machine_type,
                "run_label": run.run_label,
                "failure_count": run.failure_count,
            }
        ]
        upsert_chunks(
            get_sensor_collection(),
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        upsert_chunks(
            get_bot_sensor_collection(),
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        document.status = "completed"
    except Exception:
        document.status = "failed"
        document.rejection_reason = "chroma_upsert_failed"
        logger.exception("_close_run_and_build_chunk: failed to upsert run chunk to Chroma")

    run.document_id = document.id
    db.commit()


def assign_run_id(new_reading: SensorReadingIn, db: Session, machine_id: str) -> SensorRun:
    """Section 6.3 — determine the last open run for this `machine_id`, or open
    a new one. Filtered by machine_id so a reading from one machine never
    lands in another machine's run.

    Same-run rule: tool_wear_min must be non-decreasing AND the elapsed
    wall-clock time between the two readings must be within
    settings.RUN_SYNC_TOLERANCE_MINUTES of the tool-wear delta — tool wear
    normally accumulates roughly 1:1 with real time during continuous
    operation, so a reading whose wear/time relationship is wildly out of
    sync (e.g. a large real-world gap, or replayed/duplicate data) starts a
    new run even though wear itself didn't decrease. A wear decrease still
    always forces a new run on its own, unchanged from before.

    AND the elapsed time itself must be within
    settings.RUN_MAX_SAME_RUN_GAP_MINUTES — a hard cap independent of the
    sync check above, since a fixed-cadence source (e.g. SimulationManager)
    can keep wear perfectly in sync with elapsed time forever, which would
    never trip the sync-tolerance check on its own and let one run grow
    without bound."""
    open_run = (
        db.query(SensorRun)
        .filter_by(is_closed=False, machine_id=machine_id)
        .order_by(SensorRun.created_at.desc())
        .first()
    )

    if open_run is None:
        return _open_new_run(db, machine_id, new_reading)

    last_reading = (
        db.query(SensorReading)
        .filter_by(run_id=open_run.id)
        .order_by(SensorReading.reading_timestamp.desc())
        .first()
    )

    if last_reading is None:
        return _open_new_run(db, machine_id, new_reading)

    wear_delta = float(new_reading.tool_wear_min) - float(last_reading.tool_wear_min)
    timestamp_delta_minutes = (
        new_reading.timestamp - last_reading.reading_timestamp
    ).total_seconds() / 60

    same_run = (
        wear_delta >= 0
        and abs(timestamp_delta_minutes - wear_delta) <= settings.RUN_SYNC_TOLERANCE_MINUTES
        and timestamp_delta_minutes <= settings.RUN_MAX_SAME_RUN_GAP_MINUTES
    )

    if same_run:
        open_run.sample_count += 1
        open_run.end_timestamp = new_reading.timestamp
        # `failure_count` TIDAK di-increment di sini lagi: machine_failure untuk
        # new_reading belum diketahui (belum diprediksi model). Di-increment
        # setelah prediksi selesai, lihat `_bump_failure_count_if_needed`.
        db.commit()
        db.refresh(open_run)
        return open_run

    open_run.is_closed = True
    db.commit()
    _close_run_and_build_chunk(db, open_run)
    return _open_new_run(db, machine_id, new_reading)


def _bump_failure_count_if_needed(db: Session, run: SensorRun, predicted_label: bool) -> None:
    """Dipanggil SETELAH predict_failure() diketahui untuk reading yang baru saja
    ditambahkan ke `run` ini (baik run baru maupun run yang sudah ada) — Section
    6.3's `failure_count` harus dihitung dari hasil prediksi model, bukan dari
    input user (yang sudah dihapus, lihat Perubahan 1)."""
    if predicted_label:
        run.failure_count += 1
        db.commit()
        db.refresh(run)



import threading
import time
from datetime import datetime, timedelta
import random

class SimulationManager:
    _tasks = {}
    _state = {}
    _stop_events = {}

    @classmethod
    def start_simulation(cls, machine_id: str):
        if machine_id in cls._tasks and cls._tasks[machine_id].is_alive():
            return
        cls._state[machine_id] = {"tool_wear": 0.0}
        stop_event = threading.Event()
        cls._stop_events[machine_id] = stop_event
        t = threading.Thread(target=cls._run_simulation, args=(machine_id, stop_event), daemon=True)
        cls._tasks[machine_id] = t
        t.start()

    @classmethod
    def restart_simulation(cls, machine_id: str):
        if machine_id in cls._stop_events:
            cls._stop_events[machine_id].set()
        cls._state[machine_id] = {"tool_wear": 0.0}
        stop_event = threading.Event()
        cls._stop_events[machine_id] = stop_event
        t = threading.Thread(target=cls._run_simulation, args=(machine_id, stop_event), daemon=True)
        cls._tasks[machine_id] = t
        t.start()

    @classmethod
    def start_all(cls, db: Session) -> int:
        """Starts (or leaves already-running) simulation for every machine in
        the DB — used by the app startup hook (main.py) so a freshly
        (re)started backend process resumes producing demo data on its own,
        instead of staying dormant until some reading arrives through
        submit_reading() to re-trigger it. Returns how many machines it
        applied to."""
        machine_ids = [str(m.id) for m in db.query(Machine).all()]
        for machine_id in machine_ids:
            cls.start_simulation(machine_id)
        return len(machine_ids)

    @classmethod
    def stop_simulation(cls, machine_id: str):
        if machine_id in cls._stop_events:
            cls._stop_events[machine_id].set()

    @classmethod
    def _run_simulation(cls, machine_id: str, stop_event: threading.Event):
        from app.db.session import SessionLocal
        from app.db.models import SensorReading, Machine
        from app.ml.predictor_clasification import predict_failure
        from app.schemas.sensor import SensorReadingIn
        try:
            while not stop_event.is_set():
                # Wait 2 minutes (120 seconds), but check stop_event every second so it can be interrupted quickly
                for _ in range(120):
                    if stop_event.is_set():
                        return
                    time.sleep(1)
                    
                db = SessionLocal()
                try:
                    machine = db.query(Machine).filter(Machine.id == machine_id).first()
                    if not machine:
                        break

                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                    
                    air_temp = round(random.uniform(298.0, 300.0), 1)
                    proc_temp = round(air_temp + random.uniform(10.0, 11.0), 1)
                    rpm = random.randint(1300, 2000)
                    
                    # Tool wear increases by 2.0 every 2 minutes
                    cls._state[machine_id]["tool_wear"] += 2.0
                    
                    item = SensorReadingIn(
                        timestamp=now,
                        air_temperature_k=air_temp,
                        process_temperature_k=proc_temp,
                        rotational_speed_rpm=rpm,
                        tool_wear_min=round(cls._state[machine_id]["tool_wear"], 2)
                    )
                    
                    run = assign_run_id(item, db, machine_id)
                    reading = SensorReading(
                        run_id=run.id,
                        reading_timestamp=item.timestamp,
                        air_temperature_k=item.air_temperature_k,
                        process_temperature_k=item.process_temperature_k,
                        rotational_speed_rpm=item.rotational_speed_rpm,
                        tool_wear_min=item.tool_wear_min,
                        machine_failure=None,
                        input_source="simulation",
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
                    
                    # Because there is only 1 row, we always trigger the report pipeline
                    report = None
                    try:
                        report = _run_report_pipeline(db, reading, pred_result, machine_id)
                    except Exception as e:
                        logger.error(f"Simulation pipeline error: {e}")
                    
                    notify_new_reading(
                                machine.name,
                                pred_result,
                                horizon_probability=report.horizon_prediction.failure_probability if report and report.horizon_prediction else None,
                                horizon_minutes=report.horizon_prediction.horizon_minutes if report and report.horizon_prediction else None,
                                run_label=run.run_label,
                                health_score=report.prediction.health_score if report else None,
                                top_feature_name=report.shap.features[0].feature_name if report and report.shap.features else None,
                                cause_analysis_short=report.cause_analysis_short if report else None,
                            )
                except Exception as e:
                    logger.error(f"Error in simulation task: {e}")
                finally:
                    db.close()
        except Exception as e:
            logger.error(f"Simulation thread crashed: {e}")



@router.post("/readings", response_model=SensorReadingSubmitResponseOut)
def submit_reading(
    payload: SensorReadingIn,
    machine_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
    _: None = Depends(_require_direct_localhost_request),
):
    machine = _require_machine(db, machine_id)
    if _is_zero_reading(payload):
        # TEMPORARY DIAGNOSTIC — 400 rejection disabled to see which field is
        # actually 0 on incoming readings; re-enable the raise below once
        # confirmed. Logs the zero field(s) instead of blocking the request.
        zero_fields = [
            name
            for name, value in (
                ("air_temperature_k", payload.air_temperature_k),
                ("process_temperature_k", payload.process_temperature_k),
                ("rotational_speed_rpm", payload.rotational_speed_rpm),
                ("tool_wear_min", payload.tool_wear_min),
            )
            if value == 0
        ]
        logger.warning(
            "submit_reading: DIAGNOSTIC — zero-value reading let through, "
            "machine=%s zero_fields=%s payload=%s",
            machine_id,
            zero_fields,
            payload.model_dump(),
        )
        # raise HTTPException(
        #     status_code=400,
        #     detail=(
        #         "Invalid sensor reading: one or more values is 0 "
        #         "(air_temperature_k, process_temperature_k, rotational_speed_rpm, "
        #         "tool_wear_min), which indicates a disconnected/faulty sensor."
        #     ),
        # )
        
    SimulationManager.start_simulation(machine_id)
        
    run = assign_run_id(payload, db, machine_id)
    reading = SensorReading(
        run_id=run.id,
        reading_timestamp=payload.timestamp,
        air_temperature_k=payload.air_temperature_k,
        process_temperature_k=payload.process_temperature_k,
        rotational_speed_rpm=payload.rotational_speed_rpm,
        tool_wear_min=payload.tool_wear_min,
        machine_failure=None,
        input_source="manual_form",
        created_by=user.id if user else None,
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)

    # --- machine_failure sekarang HASIL prediksi model, bukan input user
    # (Perubahan 1). Jalankan predict_failure() dengan 4 fitur mentah SETELAH
    # reading tersimpan, lalu update reading.machine_failure + run.failure_count. ---
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

    # --- Perubahan 2: pipeline SHAP/KNN/CRAG/laporan LLM dijalankan SEKALI di
    # sini, saat data sensor baru masuk — bukan lagi tiap kali GET /report/latest
    # dipanggil. pred_result yang sudah dihitung di atas dipakai ulang (TIDAK
    # panggil predict_failure() dua kali) — lihat _run_report_pipeline signature. ---
    report = None
    try:
        report = _run_report_pipeline(db, reading, pred_result, machine_id)
    except Exception:
        logger.exception(
            "submit_reading: _run_report_pipeline failed for reading %s — "
            "GET /report/latest will 404 until this is retried/regenerated",
            reading.id,
        )

    # notify_new_reading() called after the pipeline (not right after
    # pred_result) so the Telegram message can include the horizon model's
    # "+N Minute" probability too — that's only known once the pipeline
    # (which computes it) has run. report stays None if the pipeline failed
    # above; notify_new_reading() just omits the horizon line in that case.
    notify_new_reading(
        machine.name,
        pred_result,
        horizon_probability=report.horizon_prediction.failure_probability if report and report.horizon_prediction else None,
        horizon_minutes=report.horizon_prediction.horizon_minutes if report and report.horizon_prediction else None,
        run_label=run.run_label,
        health_score=report.prediction.health_score if report else None,
        top_feature_name=report.shap.features[0].feature_name if report and report.shap.features else None,
        cause_analysis_short=report.cause_analysis_short if report else None,
    )

    return SensorReadingSubmitResponseOut(
        reading=SensorReadingOut(
            id=str(reading.id),
            run_id=str(reading.run_id) if reading.run_id else None,
            reading_timestamp=reading.reading_timestamp,
            air_temperature_k=float(reading.air_temperature_k),
            process_temperature_k=float(reading.process_temperature_k),
            rotational_speed_rpm=reading.rotational_speed_rpm,
            tool_wear_min=float(reading.tool_wear_min),
            machine_failure=reading.machine_failure,
            input_source=reading.input_source,
        ),
        run=SensorRunOut(
            id=str(run.id),
            run_label=run.run_label,
            start_timestamp=run.start_timestamp,
            end_timestamp=run.end_timestamp,
            sample_count=run.sample_count,
            failure_count=run.failure_count,
            is_closed=run.is_closed,
        ),
    )


@router.post("/reading", response_model=SensorReadingSubmitResponseOut)
def submit_single_reading_and_stop(
    payload: SensorReadingIn,
    machine_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
    _: None = Depends(_require_direct_localhost_request),
):
    machine = _require_machine(db, machine_id)
    if _is_zero_reading(payload):
        zero_fields = [
            name
            for name, value in (
                ("air_temperature_k", payload.air_temperature_k),
                ("process_temperature_k", payload.process_temperature_k),
                ("rotational_speed_rpm", payload.rotational_speed_rpm),
                ("tool_wear_min", payload.tool_wear_min),
            )
            if value == 0
        ]
        logger.warning(
            "submit_single_reading_and_stop: DIAGNOSTIC — zero-value reading let through, "
            "machine=%s zero_fields=%s payload=%s",
            machine_id,
            zero_fields,
            payload.model_dump(),
        )
        
    SimulationManager.stop_simulation(machine_id)
        
    run = assign_run_id(payload, db, machine_id)
    reading = SensorReading(
        run_id=run.id,
        reading_timestamp=payload.timestamp,
        air_temperature_k=payload.air_temperature_k,
        process_temperature_k=payload.process_temperature_k,
        rotational_speed_rpm=payload.rotational_speed_rpm,
        tool_wear_min=payload.tool_wear_min,
        machine_failure=None,
        input_source="manual_form",
        created_by=user.id if user else None,
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

    report = None
    try:
        report = _run_report_pipeline(db, reading, pred_result, machine_id)
    except Exception:
        logger.exception(
            "submit_single_reading_and_stop: _run_report_pipeline failed for reading %s",
            reading.id,
        )

    notify_new_reading(
        machine.name,
        pred_result,
        horizon_probability=report.horizon_prediction.failure_probability if report and report.horizon_prediction else None,
        horizon_minutes=report.horizon_prediction.horizon_minutes if report and report.horizon_prediction else None,
        run_label=run.run_label,
        health_score=report.prediction.health_score if report else None,
        top_feature_name=report.shap.features[0].feature_name if report and report.shap.features else None,
        cause_analysis_short=report.cause_analysis_short if report else None,
    )

    return SensorReadingSubmitResponseOut(
        reading=SensorReadingOut(
            id=str(reading.id),
            run_id=str(reading.run_id) if reading.run_id else None,
            reading_timestamp=reading.reading_timestamp,
            air_temperature_k=float(reading.air_temperature_k),
            process_temperature_k=float(reading.process_temperature_k),
            rotational_speed_rpm=reading.rotational_speed_rpm,
            tool_wear_min=float(reading.tool_wear_min),
            machine_failure=reading.machine_failure,
            input_source=reading.input_source,
        ),
        run=SensorRunOut(
            id=str(run.id),
            run_label=run.run_label,
            start_timestamp=run.start_timestamp,
            end_timestamp=run.end_timestamp,
            sample_count=run.sample_count,
            failure_count=run.failure_count,
            is_closed=run.is_closed,
        ),
    )


@router.post("/readings/batch", response_model=list[SensorReadingOut])
def submit_readings_batch(
    payload: SensorReadingBatchIn,
    machine_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(_require_direct_localhost_request),
):
    """Endpoint API untuk DAG (input otomatis, bulk) — Section 7. Belum dipakai
    DAG saat ini, disiapkan supaya integrasi Airflow/Prefect nanti tinggal panggil."""
    machine = _require_machine(db, machine_id)
    out = []
    for item in payload.readings:
        if _is_zero_reading(item):
            logger.warning(
                "submit_readings_batch: skipping reading at %s for machine %s — "
                "one or more values is 0 (disconnected/faulty sensor)",
                item.timestamp,
                machine_id,
            )
            continue
        run = assign_run_id(item, db, machine_id)
        reading = SensorReading(
            run_id=run.id,
            reading_timestamp=item.timestamp,
            air_temperature_k=item.air_temperature_k,
            process_temperature_k=item.process_temperature_k,
            rotational_speed_rpm=item.rotational_speed_rpm,
            tool_wear_min=item.tool_wear_min,
            machine_failure=None,
            input_source="api_dag",
        )
        db.add(reading)
        db.commit()
        db.refresh(reading)

        # Sama seperti submit_reading(): machine_failure adalah hasil prediksi,
        # bukan input DAG (Perubahan 1), dan pipeline report dipicu sekali di sini
        # per reading (Perubahan 2).
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

        report = None
        try:
            report = _run_report_pipeline(db, reading, pred_result, machine_id)
        except Exception:
            logger.exception(
                "submit_readings_batch: _run_report_pipeline failed for reading %s",
                reading.id,
            )

        notify_new_reading(
            machine.name,
            pred_result,
            horizon_probability=report.horizon_prediction.failure_probability if report and report.horizon_prediction else None,
            horizon_minutes=report.horizon_prediction.horizon_minutes if report and report.horizon_prediction else None,
            run_label=run.run_label,
            health_score=report.prediction.health_score if report else None,
            top_feature_name=report.shap.features[0].feature_name if report and report.shap.features else None,
            cause_analysis_short=report.cause_analysis_short if report else None,
        )

        out.append(
            SensorReadingOut(
                id=str(reading.id),
                run_id=str(reading.run_id) if reading.run_id else None,
                reading_timestamp=reading.reading_timestamp,
                air_temperature_k=float(reading.air_temperature_k),
                process_temperature_k=float(reading.process_temperature_k),
                rotational_speed_rpm=reading.rotational_speed_rpm,
                tool_wear_min=float(reading.tool_wear_min),
                machine_failure=reading.machine_failure,
                input_source=reading.input_source,
            )
        )
    return out


@router.get("/runs", response_model=list[SensorRunOut])
def list_runs(machine_id: str, db: Session = Depends(get_db)):
    runs = (
        db.query(SensorRun)
        .filter(SensorRun.machine_id == machine_id)
        .order_by(SensorRun.created_at.desc())
        .all()
    )
    return [
        SensorRunOut(
            id=str(r.id),
            run_label=r.run_label,
            start_timestamp=r.start_timestamp,
            end_timestamp=r.end_timestamp,
            sample_count=r.sample_count,
            failure_count=r.failure_count,
            is_closed=r.is_closed,
        )
        for r in runs
    ]


def _is_anomaly(air_k: float, process_k: float, rpm: int, wear: float, bounds: RunIqrBounds) -> bool:
    """IQR outlier check (rancangan.txt: "outlier detection menggunakan IQR
    untuk setiap RUN ID") — bounds dihitung on-the-fly dari readings dalam run
    yang sama (lihat app/ml/outlier.py), bukan dari bound statis global
    training seperti sebelumnya. Anomaly kalau SALAH SATU dari 4 parameter
    mentah berada di luar bound Tukey (Q1-1.5*IQR, Q3+1.5*IQR) run ini."""
    return (
        is_value_outlier(air_k, bounds.air_temperature_k)
        or is_value_outlier(process_k, bounds.process_temperature_k)
        or is_value_outlier(rpm, bounds.rotational_speed_rpm)
        or is_value_outlier(wear, bounds.tool_wear_min)
    )


def _param_stats(values: list[float]) -> SensorParamStatsOut:
    if not values:
        return SensorParamStatsOut(min=None, max=None, avg=None, current=None)
    return SensorParamStatsOut(
        min=min(values),
        max=max(values),
        avg=round(statistics.fmean(values), 2),
        current=values[-1],
    )


@router.get("/readings/history", response_model=SensorHistoryOut)
def get_readings_history(machine_id: str, db: Session = Depends(get_db)):
    """Section "Sensor Monitoring" dashboard — line chart 4 parameter untuk SATU
    run (run terbaru mesin ini), bukan gabungan lintas-run. tool_wear_min naik
    monoton di dalam satu run lalu jatuh balik ke ~0 begitu run baru mulai
    (lihat dataset.csv), sehingga menggabungkan beberapa run dalam satu chart
    menghasilkan grafik gigi-gergaji yang menyesatkan — scoping ke run terbaru
    menghindari itu sekaligus otomatis mengikuti "perpotongan" run terbaru."""
    latest_run = (
        db.query(SensorRun)
        .filter(SensorRun.machine_id == machine_id)
        .order_by(SensorRun.start_timestamp.desc())
        .first()
    )
    if latest_run is None:
        return SensorHistoryOut(
            run_label=None,
            points=[],
            air_temperature_k=_param_stats([]),
            process_temperature_k=_param_stats([]),
            rotational_speed_rpm=_param_stats([]),
            tool_wear_min=_param_stats([]),
        )

    rows = (
        db.query(SensorReading)
        .filter(SensorReading.run_id == latest_run.id)
        .order_by(SensorReading.reading_timestamp.asc())
        .all()
    )

    run_bounds = compute_run_iqr_bounds(
        [
            {
                "air_temperature_k": r.air_temperature_k,
                "process_temperature_k": r.process_temperature_k,
                "rotational_speed_rpm": r.rotational_speed_rpm,
                "tool_wear_min": r.tool_wear_min,
            }
            for r in rows
        ]
    )

    points = []
    air_vals, proc_vals, rpm_vals, wear_vals = [], [], [], []
    for r in rows:
        air = float(r.air_temperature_k)
        proc = float(r.process_temperature_k)
        rpm = int(r.rotational_speed_rpm)
        wear = float(r.tool_wear_min)
        air_vals.append(air)
        proc_vals.append(proc)
        rpm_vals.append(rpm)
        wear_vals.append(wear)
        points.append(
            SensorHistoryPointOut(
                timestamp=r.reading_timestamp,
                air_temperature_k=air,
                process_temperature_k=proc,
                rotational_speed_rpm=rpm,
                tool_wear_min=wear,
                is_anomaly=_is_anomaly(air, proc, rpm, wear, run_bounds),
            )
        )

    return SensorHistoryOut(
        run_label=latest_run.run_label,
        points=points,
        air_temperature_k=_param_stats(air_vals),
        process_temperature_k=_param_stats(proc_vals),
        rotational_speed_rpm=_param_stats(rpm_vals),
        tool_wear_min=_param_stats(wear_vals),
    )


# --- Added for Simulation ---
import csv
import os
import random
from datetime import datetime, timedelta
from fastapi import Query
from pydantic import BaseModel

class SimulationResponse(BaseModel):
    message: str
    file_path: str
    num_rows: int
    preview: list[dict]

@router.post("/simulate-csv", response_model=SimulationResponse)
def simulate_cnc_data(num_rows: int = Query(100, description="Number of rows to generate")):
    """
    Generates healthy CNC milling machine data into a CSV file.
    Each row represents a 5-minute interval.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    saved_dir = os.path.join(base_dir, "saved")
    os.makedirs(saved_dir, exist_ok=True)
    
    file_path = os.path.join(saved_dir, "healthy_cnc_data.csv")
    
    start_time = datetime.now()
    
    data = []
    
    for i in range(num_rows):
        current_time = start_time + timedelta(minutes=5 * i)
        
        # Base healthy values
        air_temp = round(random.uniform(298.0, 300.0), 1)
        proc_temp = round(air_temp + random.uniform(10.0, 11.0), 1)
        rpm = random.randint(1300, 2000)
        
        # Tool wear increases by 5 each 5 minutes
        current_wear = i * 5
        
        row = {
            "Timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "Air temperature K": air_temp,
            "Process temperature K": proc_temp,
            "Rotational speed rpm": rpm,
            "Tool wear min": current_wear,
            "Machine failure": 0
        }
        data.append(row)
        
    # Write to CSV
    headers = ["Timestamp", "Air temperature K", "Process temperature K", "Rotational speed rpm", "Tool wear min", "Machine failure"]
    with open(file_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)
        
    return SimulationResponse(
        message="Successfully generated healthy CNC data",
        file_path=file_path,
        num_rows=num_rows,
        preview=data[:5]
    )


@router.post("/machine-diagnosis")
def machine_diagnosis(machine_id: str):
    SimulationManager.restart_simulation(machine_id)
    return {"message": f"Simulation restarted for machine {machine_id}"}
