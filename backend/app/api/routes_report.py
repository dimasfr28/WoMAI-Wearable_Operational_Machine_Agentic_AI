"""Section 7: GET /report/latest, GET /report/history — implements Section 6.11 pipeline."""
from __future__ import annotations

import logging

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentChunk,
    FinalReport,
    Machine,
    PartPriceLookup,
    Prediction,
    Recommendation,
    RootCauseAnalysis,
    SensorReading,
    SensorRun,
    ShapExplanation,
)
from app.db.session import get_db
from app.config import settings
from app.ml.knn_tool import recommend_similar_cases, worst_case_delta
from app.ml.predictor import RAW_TO_MODEL_COL, PredictionResult, get_model_bundle
from app.ml.shap_tool import explain_failure_shap
from app.rag.crag_graph import generate_search_queries, run_crag
from app.rag.final_report import FinalReportContext, generate_final_report
from app.rag.part_price_search import search_part_price
from app.schemas.report import (
    PartPriceOut,
    PredictionOut,
    RecommendationsOut,
    ReportHistoryItemOut,
    ReportOut,
    RetrievedChunkOut,
    RootCauseOut,
    SensorSnapshotOut,
    ShapExplanationOut,
    ShapFeatureOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report", tags=["report"])

RAW_FEATURE_COLS = ["air_temperature_k", "process_temperature_k", "rotational_speed_rpm", "tool_wear_min"]


def _historical_df(db: Session, machine_id: str, limit: int = 5000) -> pd.DataFrame:
    """Ambil sensor_readings berlabel (machine_failure IS NOT NULL) MILIK machine_id
    ini sbg background/KNN data — join lewat sensor_runs supaya SHAP/KNN untuk satu
    mesin tidak pernah "belajar" dari data mesin lain yang mungkin punya karakteristik
    berbeda."""
    rows = (
        db.query(SensorReading)
        .join(SensorRun, SensorRun.id == SensorReading.run_id)
        .filter(SensorReading.machine_failure.isnot(None), SensorRun.machine_id == machine_id)
        .order_by(SensorReading.reading_timestamp.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return pd.DataFrame(columns=RAW_FEATURE_COLS + ["machine_failure"])
    return pd.DataFrame(
        [
            {
                "air_temperature_k": float(r.air_temperature_k),
                "process_temperature_k": float(r.process_temperature_k),
                "rotational_speed_rpm": int(r.rotational_speed_rpm),
                "tool_wear_min": float(r.tool_wear_min),
                "machine_failure": bool(r.machine_failure),
            }
            for r in rows
        ]
    )


def _run_report_pipeline(
    db: Session, sensor_reading: SensorReading, pred_result: PredictionResult, machine_id: str
) -> ReportOut:
    """Section 6.11 pipeline penuh: SHAP -> KNN/worst-case-delta -> CRAG RAG (kalau
    predicted failure) -> harga part -> laporan akhir LLM. Disimpan ke predictions,
    shap_explanations, recommendations, root_cause_analyses, part_price_lookups,
    final_reports.

    Perubahan 2 (report digenerate sekali saat data masuk, bukan tiap GET):
    dipanggil SEKALI dari routes_sensor.py's submit_reading()/submit_readings_batch()
    setelah reading tersimpan.

    Perubahan 1 + optimisasi: `pred_result` diterima sebagai parameter (BUKAN
    dihitung ulang di sini) karena predict_failure() SUDAH dipanggil di
    submit_reading() untuk mengisi reading.machine_failure — memanggilnya lagi di
    sini akan boros dan berisiko inkonsisten kalau model bundle reload di antara
    dua panggilan.
    """
    feature_row = {
        "air_temperature_k": float(sensor_reading.air_temperature_k),
        "process_temperature_k": float(sensor_reading.process_temperature_k),
        "rotational_speed_rpm": int(sensor_reading.rotational_speed_rpm),
        "tool_wear_min": float(sensor_reading.tool_wear_min),
    }

    # --- 6.6 Prediksi: SUDAH dihitung oleh caller (submit_reading), pakai ulang ---
    prediction = Prediction(
        sensor_reading_id=sensor_reading.id,
        predicted_label=pred_result.label,
        failure_probability=round(pred_result.probability, 4),
        model_version=pred_result.model_version,
    )
    db.add(prediction)
    db.commit()
    db.refresh(prediction)

    historical_df = _historical_df(db, machine_id)

    # --- 6.7 SHAP ---
    if len(historical_df) >= 5:
        shap_result = explain_failure_shap(feature_row, historical_df)
    else:
        # Not enough historical labeled data yet for a meaningful background set.
        shap_result = {
            "base_value": pred_result.probability,
            "features": [
                {"feature_name": RAW_TO_MODEL_COL[f], "value": feature_row[f], "shap_value": 0.0, "rank": i + 1}
                for i, f in enumerate(RAW_FEATURE_COLS)
            ],
        }

    # Persist base_value on the prediction row itself (not per-feature) so
    # GET /report/latest can rebuild ShapExplanationOut.base_value from the DB
    # without re-running SHAP.
    prediction.shap_base_value = round(float(shap_result["base_value"]), 6)
    db.add(prediction)

    for f in shap_result["features"]:
        db.add(
            ShapExplanation(
                prediction_id=prediction.id,
                feature_name=f["feature_name"],
                feature_value=f["value"],
                shap_value=f["shap_value"],
                rank=f["rank"],
            )
        )
    db.commit()

    # --- 6.8 KNN + worst-case delta ---
    if len(historical_df) >= 2 and historical_df["machine_failure"].nunique() == 2:
        knn_result = recommend_similar_cases(feature_row, historical_df)
        wc_delta = worst_case_delta(feature_row, historical_df)
    else:
        knn_result = {"nearest_failure": {"distances": [], "rows": []}, "nearest_no_failure": {"distances": [], "rows": []}}
        wc_delta = {"nearest_safe_point": None, "suggested_adjustments": {}}

    db.add(Recommendation(prediction_id=prediction.id, recommendation_type="nearest_failure", payload=knn_result["nearest_failure"]))
    db.add(Recommendation(prediction_id=prediction.id, recommendation_type="nearest_no_failure", payload=knn_result["nearest_no_failure"]))
    db.add(Recommendation(prediction_id=prediction.id, recommendation_type="worst_case_delta", payload=wc_delta))
    db.commit()

    # --- 6.9 / 6.10 RAG + part price (only if predicted failure) ---
    root_cause_out: RootCauseOut | None = None
    part_price_out: list[PartPriceOut] = []

    if pred_result.label:
        machine_row = db.query(Machine).filter(Machine.id == machine_id).first()
        machine_name = machine_row.name if machine_row else "CNC machine"

        top_shap_term, search_queries = generate_search_queries(
            shap_result, machine_name=machine_name, feature_row=feature_row
        )
        # query_text: representasi ringkas satu-baris (disimpan di RootCauseAnalysis.
        # rag_query untuk ditampilkan di UI/dipakai grading) — search_queries (list)
        # yang benar-benar drive multi-query retrieval di run_crag()/retrieve().
        query_text = f"{machine_name}: {top_shap_term} — " + "; ".join(search_queries[:2])
        try:
            crag_state = run_crag(query_text, machine_id=machine_id, search_queries=search_queries)
        except Exception:
            logger.exception("_run_report_pipeline: CRAG invocation failed")
            crag_state = {
                "answer": "Analisis root cause tidak dapat dijalankan (RAG service error).",
                "used_web_fallback": False,
                "documents": [],
                "part_name": None,
            }

        retrieved_ids = [
            d.metadata.get("postgres_chunk_id")
            for d in crag_state.get("documents", [])
            if d.metadata.get("postgres_chunk_id")
        ]
        # Transparansi (revisi rancangan.txt): tunjukkan isi chunk yang benar-benar
        # dipakai LLM, bukan cuma ID-nya. Dibangun langsung dari crag_state["documents"]
        # (sudah bawa page_content + metadata dari retrieve_documents) di titik ini,
        # bukan query ulang ke Postgres — web-fallback docs (tanpa postgres_chunk_id)
        # juga ikut ditampilkan lewat chunk_id="web:<url>" supaya sumbernya tetap jelas.
        retrieved_chunks_out = [
            RetrievedChunkOut(
                chunk_id=d.metadata.get("postgres_chunk_id") or f"web:{d.metadata.get('url', '?')}",
                doc_name=d.metadata.get("doc") or d.metadata.get("title"),
                heading_1=d.metadata.get("heading_1") or None,
                heading_2=d.metadata.get("heading_2") or None,
                content=d.page_content,
            )
            for d in crag_state.get("documents", [])
        ]
        rca = RootCauseAnalysis(
            prediction_id=prediction.id,
            rag_query=query_text,
            rag_answer=crag_state["answer"],
            retrieved_chunk_ids=retrieved_ids,
            used_web_fallback=crag_state.get("used_web_fallback", False),
        )
        db.add(rca)
        db.commit()

        root_cause_out = RootCauseOut(
            query=query_text,
            answer=crag_state["answer"],
            used_web_fallback=crag_state.get("used_web_fallback", False),
            retrieved_chunk_ids=retrieved_ids,
            retrieved_chunks=retrieved_chunks_out,
        )

        part_name = crag_state.get("part_name")
        if part_name:
            try:
                price_lookups = search_part_price(part_name)
            except Exception:
                logger.exception("_run_report_pipeline: part price search failed")
                price_lookups = []
            for lookup in price_lookups:
                db.add(
                    PartPriceLookup(
                        prediction_id=prediction.id,
                        part_name=lookup["part_name"],
                        price_min=lookup["price_min"],
                        price_max=lookup["price_max"],
                        currency=lookup["currency"],
                        source_url=lookup["source_url"],
                    )
                )
                part_price_out.append(PartPriceOut(**lookup))
            db.commit()

    # --- 6.10 step 5: laporan akhir ---
    context = FinalReportContext(
        prediction={"label": pred_result.label, "probability": pred_result.probability},
        shap_top_features=shap_result["features"][:5],
        worst_case_delta=wc_delta,
        similar_cases=knn_result,
        root_cause_answer=root_cause_out.answer if root_cause_out else None,
        part_price=[p.model_dump() for p in part_price_out],
    )
    report_text = generate_final_report(context)

    final_report = FinalReport(prediction_id=prediction.id, report_text=report_text, llm_model=settings.GROQ_MODEL)
    db.add(final_report)
    db.commit()
    db.refresh(final_report)

    return ReportOut(
        sensor=SensorSnapshotOut(
            id=str(sensor_reading.id),
            reading_timestamp=sensor_reading.reading_timestamp,
            **feature_row,
        ),
        prediction=PredictionOut(
            id=str(prediction.id),
            predicted_label=prediction.predicted_label,
            failure_probability=float(prediction.failure_probability),
            health_score=round((1 - float(prediction.failure_probability)) * 100, 2),
            model_version=prediction.model_version,
            threshold=pred_result.threshold,
        ),
        shap=ShapExplanationOut(
            base_value=shap_result["base_value"],
            features=[ShapFeatureOut(**f) for f in shap_result["features"]],
        ),
        recommendations=RecommendationsOut(
            nearest_failure=knn_result["nearest_failure"],
            nearest_no_failure=knn_result["nearest_no_failure"],
            worst_case_delta=wc_delta,
        ),
        root_cause=root_cause_out,
        part_prices=part_price_out,
        final_report_text=report_text,
        llm_model=settings.GROQ_MODEL,
        created_at=final_report.created_at,
    )


@router.get("/latest", response_model=ReportOut)
def get_latest_report(machine_id: str, db: Session = Depends(get_db)):
    """Perubahan 2: TIDAK generate apapun lagi di sini — report sudah dibuat SEKALI
    oleh routes_sensor.py's submit_reading() saat data sensor masuk (lihat
    _run_report_pipeline). Endpoint ini murni query DB, jadi harus cepat (tidak ada
    panggilan LLM/SHAP/KNN/CRAG di request path GET ini)."""
    sensor_reading = (
        db.query(SensorReading)
        .join(SensorRun, SensorRun.id == SensorReading.run_id)
        .filter(SensorRun.machine_id == machine_id)
        .order_by(SensorReading.reading_timestamp.desc())
        .first()
    )
    if sensor_reading is None:
        raise HTTPException(status_code=404, detail="Belum ada data sensor. Input data sensor terlebih dahulu.")

    prediction = (
        db.query(Prediction)
        .filter(Prediction.sensor_reading_id == sensor_reading.id)
        .order_by(Prediction.created_at.desc())
        .first()
    )
    if prediction is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Report belum tersedia untuk data sensor ini — kemungkinan pipeline "
                "gagal saat submit (mis. data lama sebelum fitur auto-report, atau "
                "error di SHAP/KNN/CRAG/LLM saat data ini disubmit). Cek log backend "
                "untuk sensor_reading_id="
                f"{sensor_reading.id}."
            ),
        )

    feature_row = {
        "air_temperature_k": float(sensor_reading.air_temperature_k),
        "process_temperature_k": float(sensor_reading.process_temperature_k),
        "rotational_speed_rpm": int(sensor_reading.rotational_speed_rpm),
        "tool_wear_min": float(sensor_reading.tool_wear_min),
    }

    shap_rows = (
        db.query(ShapExplanation)
        .filter(ShapExplanation.prediction_id == prediction.id)
        .order_by(ShapExplanation.rank.asc())
        .all()
    )
    shap_out = ShapExplanationOut(
        # shap_base_value is the persisted SHAP TreeExplainer expected_value (see
        # Prediction.shap_base_value / migration 0002). Falls back to
        # failure_probability only for legacy rows predating that column.
        base_value=(
            float(prediction.shap_base_value)
            if prediction.shap_base_value is not None
            else float(prediction.failure_probability)
        ),
        features=[
            ShapFeatureOut(
                feature_name=s.feature_name,
                value=float(s.feature_value),
                shap_value=float(s.shap_value),
                rank=s.rank,
            )
            for s in shap_rows
        ],
    )

    recommendations = (
        db.query(Recommendation).filter(Recommendation.prediction_id == prediction.id).all()
    )
    rec_by_type = {r.recommendation_type: r.payload for r in recommendations}
    recommendations_out = RecommendationsOut(
        nearest_failure=rec_by_type.get("nearest_failure", {"distances": [], "rows": []}),
        nearest_no_failure=rec_by_type.get("nearest_no_failure", {"distances": [], "rows": []}),
        worst_case_delta=rec_by_type.get("worst_case_delta", {"nearest_safe_point": None, "suggested_adjustments": {}}),
    )

    root_cause_out: RootCauseOut | None = None
    rca = (
        db.query(RootCauseAnalysis)
        .filter(RootCauseAnalysis.prediction_id == prediction.id)
        .order_by(RootCauseAnalysis.created_at.desc())
        .first()
    )
    if rca is not None:
        chunk_ids = [str(cid) for cid in (rca.retrieved_chunk_ids or [])]
        # Rekonstruksi isi chunk dari Postgres (Chroma metadata sendiri tidak
        # disimpan di RootCauseAnalysis, hanya ID) — web-fallback docs tak punya
        # postgres_chunk_id jadi tak bisa direkonstruksi di sini, cukup terlihat
        # dari used_web_fallback=True.
        chunk_rows = (
            db.query(DocumentChunk, Document.doc_name)
            .join(Document, Document.id == DocumentChunk.document_id)
            .filter(DocumentChunk.id.in_(chunk_ids))
            .all()
        ) if chunk_ids else []
        chunk_by_id = {str(c.id): (c, doc_name) for c, doc_name in chunk_rows}
        retrieved_chunks_out = [
            RetrievedChunkOut(
                chunk_id=cid,
                doc_name=chunk_by_id[cid][1] if cid in chunk_by_id else None,
                heading_1=chunk_by_id[cid][0].heading_1 if cid in chunk_by_id else None,
                heading_2=chunk_by_id[cid][0].heading_2 if cid in chunk_by_id else None,
                content=chunk_by_id[cid][0].content if cid in chunk_by_id else "(chunk tidak ditemukan di database)",
            )
            for cid in chunk_ids
        ]
        root_cause_out = RootCauseOut(
            query=rca.rag_query,
            answer=rca.rag_answer,
            used_web_fallback=rca.used_web_fallback,
            retrieved_chunk_ids=chunk_ids,
            retrieved_chunks=retrieved_chunks_out,
        )

    part_price_rows = (
        db.query(PartPriceLookup).filter(PartPriceLookup.prediction_id == prediction.id).all()
    )
    part_prices_out = [
        PartPriceOut(
            part_name=p.part_name,
            price_min=float(p.price_min) if p.price_min is not None else None,
            price_max=float(p.price_max) if p.price_max is not None else None,
            currency=p.currency,
            source_url=p.source_url,
        )
        for p in part_price_rows
    ]

    final_report = (
        db.query(FinalReport)
        .filter(FinalReport.prediction_id == prediction.id)
        .order_by(FinalReport.created_at.desc())
        .first()
    )
    if final_report is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Report belum tersedia untuk data sensor ini — kemungkinan pipeline "
                "gagal saat submit sebelum laporan akhir sempat dibuat. Cek log "
                f"backend untuk sensor_reading_id={sensor_reading.id}."
            ),
        )

    return ReportOut(
        sensor=SensorSnapshotOut(
            id=str(sensor_reading.id),
            reading_timestamp=sensor_reading.reading_timestamp,
            **feature_row,
        ),
        prediction=PredictionOut(
            id=str(prediction.id),
            predicted_label=prediction.predicted_label,
            failure_probability=float(prediction.failure_probability),
            health_score=round((1 - float(prediction.failure_probability)) * 100, 2),
            model_version=prediction.model_version,
            # `threshold` tidak disimpan di tabel predictions (hanya predicted_label
            # /failure_probability/model_version) — diambil dari model bundle yang
            # di-cache (lru_cache di predictor.py), BUKAN memanggil predict_failure()
            # lagi. Ini murni baca in-memory cache, jadi tetap cepat.
            threshold=get_model_bundle().optimal_threshold,
        ),
        shap=shap_out,
        recommendations=recommendations_out,
        root_cause=root_cause_out,
        part_prices=part_prices_out,
        final_report_text=final_report.report_text,
        llm_model=final_report.llm_model,
        created_at=final_report.created_at,
    )


@router.get("/history", response_model=list[ReportHistoryItemOut])
def get_report_history(machine_id: str, db: Session = Depends(get_db), limit: int = 50):
    predictions = (
        db.query(Prediction, SensorReading)
        .join(SensorReading, Prediction.sensor_reading_id == SensorReading.id)
        .join(SensorRun, SensorRun.id == SensorReading.run_id)
        .filter(SensorRun.machine_id == machine_id)
        .order_by(Prediction.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        ReportHistoryItemOut(
            prediction_id=str(pred.id),
            reading_timestamp=reading.reading_timestamp,
            predicted_label=pred.predicted_label,
            failure_probability=float(pred.failure_probability),
            created_at=pred.created_at,
        )
        for pred, reading in predictions
    ]
