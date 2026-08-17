"""Section 7: POST /sensor/readings, POST /sensor/readings/batch, GET /sensor/runs.

Not explicitly named in Section 2's file tree (which only lists routes_knowledgebase.py,
routes_report.py, routes_auth.py) but required by the Section 7 API contract table —
kept as its own module for clarity rather than overloading routes_report.py.
"""
from __future__ import annotations

import logging
import statistics

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.api.deps import get_current_user_optional, require_role
from app.api.routes_report import _run_report_pipeline
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
        raise HTTPException(status_code=404, detail="Mesin tidak ditemukan")
    return machine


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
    """Section 6.3 — tentukan run terbuka terakhir (untuk `machine_id` ini) atau
    buka run baru. Difilter by machine_id supaya reading dari satu mesin tidak
    pernah nyasar masuk run milik mesin lain.

    Aturan run murni berdasarkan tool_wear_min (naik = run sama, turun = run
    baru) — tool wear reset ke ~0 setiap kali sesi kerja baru dimulai, jadi
    penurunan adalah sinyal run baru yang bisa diandalkan tanpa perlu batas
    waktu/lompatan tambahan."""
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

    same_run = float(new_reading.tool_wear_min) >= float(last_reading.tool_wear_min)

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


@router.post("/readings", response_model=SensorReadingSubmitResponseOut)
def submit_reading(
    payload: SensorReadingIn,
    machine_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    machine = _require_machine(db, machine_id)
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
):
    """Endpoint API untuk DAG (input otomatis, bulk) — Section 7. Belum dipakai
    DAG saat ini, disiapkan supaya integrasi Airflow/Prefect nanti tinggal panggil."""
    machine = _require_machine(db, machine_id)
    out = []
    for item in payload.readings:
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
