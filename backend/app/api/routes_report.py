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
    MachineReport,
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
from app.ml.outlier import compute_run_iqr_bounds
from app.ml.predictor_clasification import RAW_TO_MODEL_COL, ClasificationResult
from app.ml.predictor_clasification import get_model_bundle as get_clasification_bundle
from app.ml.predictor_horizon import get_model_bundle as get_horizon_bundle
from app.ml.predictor_horizon import predict_failure_horizon
from app.ml.shap_tool import explain_failure_shap
from app.rag.crag_graph import extract_part_names, generate_search_queries, run_crag, summarize_cause_analysis
from app.rag.judge import evaluate_faithfulness
from app.rag.final_report import (
    EarlyWarningContext,
    FinalReportContext,
    generate_early_warning_narrative,
    generate_final_report,
    generate_suggestion_general,
)
from app.rag.part_price_search import search_part_price
from app.reports import report_folder
from app.reports.report_narrative import generate_machine_report_narrative
from app.reports.report_pdf import ConditionLogRow, format_wib, render_machine_report_pdf
from app.schemas.report import (
    HorizonPredictionOut,
    PartPriceOut,
    PredictionOut,
    RecommendationsOut,
    RecommendedActionOut,
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
# Reverse of predictor.py's RAW_TO_MODEL_COL — worst_case_delta()'s
# suggested_adjustments keys are display names (e.g. "Rotational speed rpm"),
# this maps back to the raw snake_case key needed to read feature_row/
# nearest_safe_point.
MODEL_COL_TO_RAW = {v: k for k, v in RAW_TO_MODEL_COL.items()}


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


def _build_narrative_and_condition_log(
    db: Session, machine_name: str, run_id: str | None, report_out: ReportOut
) -> tuple[str, list[ConditionLogRow]]:
    """Narrative text + Condition Log table (Section 6) for a Machine Report
    PDF. Split out of _generate_machine_report_pdf so regenerate_machine_report_pdf()
    (routes_machine_report.py's missing-file fallback) can rebuild the same
    PDF content for an already-persisted report without duplicating this
    logic."""
    predicted_label = report_out.prediction.predicted_label
    probability = report_out.prediction.failure_probability
    operating_status = "Failure" if predicted_label else ("Warning" if probability >= 0.15 else "Normal")

    narrative = generate_machine_report_narrative(
        machine_name=machine_name,
        operating_status=operating_status,
        health_score=report_out.prediction.health_score,
        failure_risk_pct=round(probability * 100, 1),
        risk_level=operating_status,
        top_feature=report_out.shap.features[0].feature_name if report_out.shap.features else "-",
        root_cause_summary=report_out.cause_analysis_short,
        recommended_action_summary=(
            f"{report_out.recommended_action.feature}: {report_out.recommended_action.why}"
            if report_out.recommended_action
            else None
        ),
    )

    # Condition Log (section 6) — this run's own readings only (not
    # cross-run history), so the PDF's log matches "1 PDF = 1 run". Capped
    # at 50 rows so a very long-running run doesn't produce an unbounded
    # table.
    history_rows = (
        db.query(Prediction, SensorReading)
        .join(SensorReading, Prediction.sensor_reading_id == SensorReading.id)
        .filter(SensorReading.run_id == run_id)
        .order_by(SensorReading.reading_timestamp.asc())
        .limit(50)
        .all()
        if run_id is not None
        else []
    )
    condition_log = [
        ConditionLogRow(
            timestamp=format_wib(reading.reading_timestamp, "%d-%m-%Y %H:%M WIB"),
            air_temperature_k=float(reading.air_temperature_k),
            process_temperature_k=float(reading.process_temperature_k),
            rotational_speed_rpm=int(reading.rotational_speed_rpm),
            tool_wear_min=float(reading.tool_wear_min),
            health_score=round((1 - float(pred.failure_probability)) * 100, 2),
            failure_risk_pct=round(float(pred.failure_probability) * 100, 1),
        )
        for pred, reading in history_rows
    ]
    return narrative, condition_log


def _generate_machine_report_pdf(
    db: Session, machine_id: str, run_id: str | None, prediction: Prediction, report_out: ReportOut
) -> None:
    """Machine Report PDF (rancangan.txt Section 7) — one row/file per run,
    not per reading: the first reading of a run creates the report, every
    later reading in that same still-open run overwrites the same file/row
    in place. Called once at the end of _run_report_pipeline, every time a
    new sensor reading comes in. Failure here must NOT fail the main
    prediction/report pipeline — the caller wraps this call in try/except."""
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    machine_name = machine.name if machine else "CNC Machine"

    predicted_label = report_out.prediction.predicted_label
    probability = report_out.prediction.failure_probability
    operating_status = "Failure" if predicted_label else ("Warning" if probability >= 0.15 else "Normal")

    narrative, condition_log = _build_narrative_and_condition_log(db, machine_name, run_id, report_out)

    # Upsert by run_id: reuse the existing report's number/file if this run
    # already has one (a later reading in the same still-open run), otherwise
    # allocate a fresh report_number/file_path (this run's first reading).
    # run_id is guarded against None explicitly — matching against
    # `MachineReport.run_id == None` would otherwise collide with legacy
    # rows created before this column existed.
    existing_report: MachineReport | None = (
        db.query(MachineReport).filter(MachineReport.run_id == run_id).first()
        if run_id is not None
        else None
    )

    if existing_report is not None:
        report_number = existing_report.report_number
        output_path = report_folder.resolve(existing_report.file_path)
    else:
        report_date = report_folder.today_utc()
        report_number = report_folder.next_report_number(db, machine_id, report_date)
        output_path = report_folder.report_path(machine_id, report_date, report_number)

    render_machine_report_pdf(
        machine_id=machine_id,
        machine_name=machine_name,
        report_number=report_number,
        report_out=report_out,
        narrative=narrative,
        condition_log=condition_log,
        output_path=output_path,
    )

    if existing_report is not None:
        existing_report.prediction_id = prediction.id
        existing_report.operating_status = operating_status
        db.add(existing_report)
    else:
        machine_report = MachineReport(
            machine_id=machine_id,
            run_id=run_id,
            prediction_id=prediction.id,
            report_number=report_number,
            file_path=report_folder.relative_path(machine_id, report_date, report_number),
            operating_status=operating_status,
        )
        db.add(machine_report)
    db.commit()


def regenerate_machine_report_pdf(db: Session, report: MachineReport) -> bool:
    """Fallback for routes_machine_report.py's _serve_pdf when a MachineReport
    row exists but its PDF file is missing from disk (REPORTS_DIR volume
    cleared independently of the DB — see commit 67e8eee's fix, which covers
    ordinary container recreation but not e.g. `docker compose down -v` or a
    fresh volume). Rebuilds the PDF at the row's already-allocated file_path
    from data that's already persisted (Prediction/SensorReading/FinalReport),
    same as GET /report/latest — no LLM/SHAP/KNN/CRAG recomputation, so this
    is safe to run inline in a GET request. Returns False (leaving the caller
    to 404) if the source rows this report depends on are gone too."""
    prediction = db.query(Prediction).filter(Prediction.id == report.prediction_id).first()
    if prediction is None:
        return False
    sensor_reading = db.query(SensorReading).filter(SensorReading.id == prediction.sensor_reading_id).first()
    final_report = db.query(FinalReport).filter(FinalReport.prediction_id == prediction.id).first()
    if sensor_reading is None or final_report is None:
        return False

    machine = db.query(Machine).filter(Machine.id == report.machine_id).first()
    machine_name = machine.name if machine else "CNC Machine"

    report_out = _build_report_out(db, sensor_reading, prediction, final_report)
    narrative, condition_log = _build_narrative_and_condition_log(
        db, machine_name, report.run_id, report_out
    )
    output_path = report_folder.resolve(report.file_path)
    render_machine_report_pdf(
        machine_id=report.machine_id,
        machine_name=machine_name,
        report_number=report.report_number,
        report_out=report_out,
        narrative=narrative,
        condition_log=condition_log,
        output_path=output_path,
    )
    return True


def _run_report_pipeline(
    db: Session, sensor_reading: SensorReading, pred_result: ClasificationResult, machine_id: str
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
    # --- Horizon ("Probability Failure in +10 Minute", rancangan.txt Section 5)
    # — model TERPISAH, dihitung sekali di sini (bukan oleh caller, karena
    # tidak dipakai untuk machine_failure/failure_count seperti pred_result
    # utama). Kegagalan model horizon TIDAK boleh menggagalkan seluruh
    # pipeline — hasilnya opsional (nullable di DB & schema). ---
    try:
        horizon_result = predict_failure_horizon(feature_row)
    except Exception:
        logger.exception("_run_report_pipeline: horizon prediction failed")
        horizon_result = None

    prediction = Prediction(
        sensor_reading_id=sensor_reading.id,
        predicted_label=pred_result.label,
        failure_probability=round(pred_result.probability, 4),
        model_version=pred_result.model_version,
        horizon_predicted_label=horizon_result.label if horizon_result else None,
        horizon_failure_probability=round(horizon_result.probability, 4) if horizon_result else None,
        horizon_model_version=horizon_result.model_version if horizon_result else None,
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

    # --- Early Warning narrative (AI Diagnosis + Recommended Action, frontend
    # /report page) — runs regardless of predicted_label, so a NORMAL result
    # still gets an explanation. feature/current/target computed here in
    # Python from wc_delta (deterministic); the LLM call only writes prose. ---
    top_feature_name = shap_result["features"][0]["feature_name"] if shap_result["features"] else "?"

    recommended_action_out: RecommendedActionOut | None = None
    suggestion_general: str | None = None
    suggested_adjustments = wc_delta.get("suggested_adjustments") or {}
    nearest_safe_point = wc_delta.get("nearest_safe_point")
    if suggested_adjustments and nearest_safe_point:
        top_adjustment_feature = max(suggested_adjustments, key=lambda k: abs(suggested_adjustments[k]))
        raw_key = MODEL_COL_TO_RAW.get(top_adjustment_feature)
        if raw_key is not None and raw_key in nearest_safe_point:
            recommended_action_out = RecommendedActionOut(
                feature=top_adjustment_feature,
                current_value=float(feature_row[raw_key]),
                target_value=float(nearest_safe_point[raw_key]),
                why="",
                expected_impact="",
            )
            # "Suggestions for Improvement LLM" (rancangan.txt Section 5) —
            # arah over/under diturunkan dari TANDA worst_case_delta (target -
            # current), bukan dinilai oleh LLM.
            direction = "increase" if suggested_adjustments[top_adjustment_feature] > 0 else "decrease"
            suggestion_general = generate_suggestion_general(top_adjustment_feature, direction)

    narrative = generate_early_warning_narrative(
        EarlyWarningContext(
            predicted_label=pred_result.label,
            probability=pred_result.probability,
            top_feature_name=top_feature_name,
            recommended_feature=recommended_action_out.feature if recommended_action_out else None,
            recommended_current=recommended_action_out.current_value if recommended_action_out else None,
            recommended_target=recommended_action_out.target_value if recommended_action_out else None,
        )
    )
    if recommended_action_out is not None:
        recommended_action_out.why = narrative["why"]
        recommended_action_out.expected_impact = narrative["expected_impact"]

    # --- 6.9 / 6.10 RAG + part price (only if predicted failure) ---
    root_cause_out: RootCauseOut | None = None
    part_price_out: list[PartPriceOut] = []
    # Default for the NORMAL case: narrative["cause_analysis"] (generated
    # above, alongside ai_explanation) — deliberately generic, names no
    # machine part, since there's no diagnosed fault to attribute to a part.
    # Overwritten below with the real CRAG-derived summary (which DOES name
    # parts) if this reading was predicted as a failure.
    cause_analysis_short: str | None = narrative.get("cause_analysis") or None

    if pred_result.label:
        machine_row = db.query(Machine).filter(Machine.id == machine_id).first()
        machine_name = machine_row.name if machine_row else "CNC machine"

        # IQR per RUN ID (rancangan.txt) — menentukan fitur SHAP mana yang
        # genuinely anomali (bukan cuma paling berkontribusi) untuk query RAG.
        run_readings = (
            db.query(SensorReading).filter(SensorReading.run_id == sensor_reading.run_id).all()
            if sensor_reading.run_id
            else []
        )
        run_bounds = compute_run_iqr_bounds(
            [
                {
                    "air_temperature_k": r.air_temperature_k,
                    "process_temperature_k": r.process_temperature_k,
                    "rotational_speed_rpm": r.rotational_speed_rpm,
                    "tool_wear_min": r.tool_wear_min,
                }
                for r in run_readings
            ]
        )

        top_shap_term, search_queries = generate_search_queries(
            shap_result, machine_name=machine_name, feature_row=feature_row, run_bounds=run_bounds
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
                "answer": "Root-cause analysis could not be run (RAG service error).",
                "used_web_fallback": False,
                "documents": [],
                "part_name": None,
            }

        faithfulness_score = evaluate_faithfulness(
            query=query_text,
            answer=crag_state["answer"],
            contexts=[d.page_content for d in crag_state.get("documents", [])],
        )
        logger.info(
            "ragas_faithfulness score=%s machine_id=%s prediction_id=%s",
            faithfulness_score,
            machine_id,
            prediction.id,
        )

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
            part_name=crag_state.get("part_name"),
            part_names=crag_state.get("part_names") or [],
        )
        cause_analysis_short = summarize_cause_analysis(crag_state["answer"])

        # Machine Report REVISI point 6: price EVERY part/consumable the
        # Handling Procedure named (crag_state["part_names"]), so Estimated
        # Machine Part Cost has one row per Machine Parts Checking row. The
        # RAG_ANSWER_PROMPT's PART_NAMES rule requires each entry to already
        # be a specific, marketplace-searchable name (not a bare generic word
        # like "filter") — search_part_price's own relevance guard is the
        # remaining safety net against a loosely-matched listing slipping
        # through for a still-too-generic name.
        part_names = crag_state.get("part_names") or []
        for part_name in part_names:
            try:
                price_lookups = search_part_price(part_name)
            except Exception:
                logger.exception("_run_report_pipeline: part price search failed for %r", part_name)
                price_lookups = []
            # Keep only the top (first) match per part — the report needs one
            # representative product/price per part, not every candidate.
            for lookup in price_lookups[:1]:
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
        if part_names:
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

    final_report = FinalReport(
        prediction_id=prediction.id,
        report_text=report_text,
        llm_model=settings.GROQ_MODEL,
        ai_explanation=narrative["ai_explanation"],
        recommended_action=recommended_action_out.model_dump() if recommended_action_out else None,
        cause_analysis_short=cause_analysis_short,
        suggestion_general=suggestion_general,
    )
    db.add(final_report)
    db.commit()
    db.refresh(final_report)

    report_out = ReportOut(
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
        horizon_prediction=(
            HorizonPredictionOut(
                predicted_label=horizon_result.label,
                failure_probability=round(horizon_result.probability, 4),
                model_version=horizon_result.model_version,
                threshold=horizon_result.threshold,
                horizon_minutes=horizon_result.horizon_minutes,
            )
            if horizon_result
            else None
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
        ai_explanation=narrative["ai_explanation"],
        recommended_action=recommended_action_out,
        cause_analysis_short=cause_analysis_short,
        suggestion_general=suggestion_general,
        final_report_text=report_text,
        llm_model=settings.GROQ_MODEL,
        created_at=final_report.created_at,
    )

    try:
        _generate_machine_report_pdf(db, machine_id, sensor_reading.run_id, prediction, report_out)
    except Exception:
        logger.exception("_run_report_pipeline: Machine Report PDF generation failed")

    return report_out


@router.get("/latest", response_model=ReportOut)
def get_latest_report(machine_id: str, db: Session = Depends(get_db)):
    """Perubahan 2: TIDAK generate apapun lagi di sini — report sudah dibuat SEKALI
    oleh routes_sensor.py's submit_reading() saat data sensor masuk (lihat
    _run_report_pipeline). Endpoint ini murni query DB, jadi harus cepat (tidak ada
    panggilan LLM/SHAP/KNN/CRAG di request path GET ini).

    Mengambil reading TERBARU YANG SUDAH PUNYA final_report — bukan reading
    paling baru secara mutlak. Kalau reading paling baru masih diproses
    (lumrah terjadi: klien seperti ESP32 submit tiap ~60 detik, sementara
    pipeline CRAG+scraping part price bisa makan 1-2 menit, jadi reading
    berikutnya sering sudah masuk sebelum reading sebelumnya kelar diproses),
    endpoint ini fallback ke report lengkap terakhir alih-alih 404 padahal
    datanya sebenarnya ada, cuma belum selesai diproses."""
    row = (
        db.query(SensorReading, Prediction, FinalReport)
        .join(SensorRun, SensorRun.id == SensorReading.run_id)
        .join(Prediction, Prediction.sensor_reading_id == SensorReading.id)
        .join(FinalReport, FinalReport.prediction_id == Prediction.id)
        .filter(SensorRun.machine_id == machine_id)
        .order_by(SensorReading.reading_timestamp.desc(), FinalReport.created_at.desc())
        .first()
    )
    if row is None:
        has_any_reading = (
            db.query(SensorReading.id)
            .join(SensorRun, SensorRun.id == SensorReading.run_id)
            .filter(SensorRun.machine_id == machine_id)
            .first()
            is not None
        )
        if not has_any_reading:
            raise HTTPException(status_code=404, detail="No sensor data yet. Submit sensor data first.")
        raise HTTPException(
            status_code=404,
            detail=(
                "Report not ready yet — the latest reading is still being processed "
                "(SHAP/KNN/CRAG/LLM) and there is no complete previous report "
                "for this machine yet. Please try again shortly."
            ),
        )
    sensor_reading, prediction, final_report = row
    return _build_report_out(db, sensor_reading, prediction, final_report)


def _build_report_out(
    db: Session, sensor_reading: SensorReading, prediction: Prediction, final_report: FinalReport
) -> ReportOut:
    """Reconstructs ReportOut purely from already-persisted DB rows — no
    LLM/SHAP/KNN/CRAG recomputation. Shared by GET /report/latest and
    regenerate_machine_report_pdf() (routes_machine_report.py's fallback when
    a MachineReport's PDF file is missing from disk but its DB row and
    source data are intact)."""
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
        rca_part_names = extract_part_names(rca.rag_answer)
        root_cause_out = RootCauseOut(
            query=rca.rag_query,
            answer=rca.rag_answer,
            used_web_fallback=rca.used_web_fallback,
            retrieved_chunk_ids=chunk_ids,
            retrieved_chunks=retrieved_chunks_out,
            part_name=rca_part_names[0] if rca_part_names else None,
            part_names=rca_part_names,
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
            # di-cache (lru_cache di predictor_clasification.py), BUKAN memanggil
            # predict_failure() lagi. Ini murni baca in-memory cache, jadi tetap cepat.
            threshold=get_clasification_bundle().threshold,
        ),
        horizon_prediction=(
            HorizonPredictionOut(
                predicted_label=prediction.horizon_predicted_label,
                failure_probability=float(prediction.horizon_failure_probability),
                model_version=prediction.horizon_model_version,
                # threshold/horizon_minutes tidak disimpan per-row (sama untuk
                # semua prediksi dari model version yang sama) — baca dari
                # bundle in-memory cache, sama seperti `threshold` di atas.
                threshold=get_horizon_bundle().threshold,
                horizon_minutes=get_horizon_bundle().horizon_minutes,
            )
            if prediction.horizon_predicted_label is not None
            else None
        ),
        shap=shap_out,
        recommendations=recommendations_out,
        root_cause=root_cause_out,
        part_prices=part_prices_out,
        ai_explanation=final_report.ai_explanation,
        recommended_action=(
            RecommendedActionOut(**final_report.recommended_action) if final_report.recommended_action else None
        ),
        cause_analysis_short=final_report.cause_analysis_short,
        suggestion_general=final_report.suggestion_general,
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
