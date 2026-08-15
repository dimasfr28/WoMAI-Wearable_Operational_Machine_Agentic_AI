from datetime import datetime

from pydantic import BaseModel


class SensorSnapshotOut(BaseModel):
    id: str
    reading_timestamp: datetime
    air_temperature_k: float
    process_temperature_k: float
    rotational_speed_rpm: int
    tool_wear_min: float


class PredictionOut(BaseModel):
    id: str
    predicted_label: bool
    failure_probability: float
    # Health Score = (1 - failure_probability) * 100 — pure inverse of the
    # model's own failure probability, not a separately trained/estimated
    # value (there's no dedicated health-scoring model). 100 = healthiest.
    health_score: float
    model_version: str
    threshold: float


class HorizonPredictionOut(BaseModel):
    """"Probability Failure in +10 Minute" (rancangan.txt Section 5) — model
    terpisah dari PredictionOut, menjawab pertanyaan berbeda ("akan gagal
    dalam N menit ke depan?", bukan "sedang gagal sekarang?")."""

    predicted_label: bool
    failure_probability: float
    model_version: str
    threshold: float
    horizon_minutes: int


class ShapFeatureOut(BaseModel):
    feature_name: str
    value: float
    shap_value: float
    rank: int


class ShapExplanationOut(BaseModel):
    base_value: float
    features: list[ShapFeatureOut]


class RecommendationsOut(BaseModel):
    nearest_failure: dict
    nearest_no_failure: dict
    worst_case_delta: dict


class RetrievedChunkOut(BaseModel):
    chunk_id: str
    doc_name: str | None = None
    heading_1: str | None = None
    heading_2: str | None = None
    content: str


class RootCauseOut(BaseModel):
    query: str
    answer: str
    used_web_fallback: bool
    retrieved_chunk_ids: list[str] = []
    retrieved_chunks: list[RetrievedChunkOut] = []
    # Generic part name from CRAG (e.g. "servo motor axis"), NOT a marketplace
    # listing title — distinct from PartPriceOut.part_name, which is the
    # specific product name matched on the marketplace for THIS part.
    part_name: str | None = None
    # Every part/consumable the Handling Procedure named as needing
    # replacement/servicing (part_name is always part_names[0] when
    # non-empty) — Machine Report REVISI point 6's Machine Parts Checking
    # table shows one row per entry here, but only part_names[0] gets a
    # marketplace price lookup (see routes_report.py's _run_report_pipeline).
    part_names: list[str] = []


class PartPriceOut(BaseModel):
    part_name: str
    price_min: float | None = None
    price_max: float | None = None
    currency: str
    source_url: str | None


class RecommendedActionOut(BaseModel):
    # feature/current_value/target_value are computed deterministically from
    # worst_case_delta (Section 6.8), NOT by the LLM — only why/expected_impact
    # are LLM-generated prose. Keeps the numbers trustworthy; see
    # generate_early_warning_narrative() in app/rag/final_report.py.
    feature: str
    current_value: float
    target_value: float
    why: str
    expected_impact: str


class ReportOut(BaseModel):
    sensor: SensorSnapshotOut
    prediction: PredictionOut
    horizon_prediction: HorizonPredictionOut | None = None
    shap: ShapExplanationOut
    recommendations: RecommendationsOut
    root_cause: RootCauseOut | None = None
    part_prices: list[PartPriceOut] = []
    ai_explanation: str | None = None
    recommended_action: RecommendedActionOut | None = None
    # Machine Diagnosis "AI Explanation" panel (rancangan.txt Section 5):
    # cause_analysis_short — versi ringkas root_cause.answer (maks 1 kalimat/
    # 40 kata, 1 part saja), None kalau predicted_label=False (CRAG tidak
    # dijalankan sama sekali untuk kondisi normal).
    cause_analysis_short: str | None = None
    # suggestion_general — saran perbaikan dalam istilah general/non-numerik
    # (mis. "turunkan heat", bukan "313.5 K -> 309 K"), arah over/under
    # diturunkan dari worst_case_delta (KNN). None kalau tidak ada rekomendasi
    # penyesuaian (data historis belum cukup).
    suggestion_general: str | None = None
    final_report_text: str
    llm_model: str
    created_at: datetime


class ReportHistoryItemOut(BaseModel):
    prediction_id: str
    reading_timestamp: datetime
    predicted_label: bool
    failure_probability: float
    created_at: datetime
