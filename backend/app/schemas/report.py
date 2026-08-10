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


class PartPriceOut(BaseModel):
    part_name: str
    price_min: float | None = None
    price_max: float | None = None
    currency: str
    source_url: str | None


class ReportOut(BaseModel):
    sensor: SensorSnapshotOut
    prediction: PredictionOut
    shap: ShapExplanationOut
    recommendations: RecommendationsOut
    root_cause: RootCauseOut | None = None
    part_prices: list[PartPriceOut] = []
    final_report_text: str
    llm_model: str
    created_at: datetime


class ReportHistoryItemOut(BaseModel):
    prediction_id: str
    reading_timestamp: datetime
    predicted_label: bool
    failure_probability: float
    created_at: datetime
