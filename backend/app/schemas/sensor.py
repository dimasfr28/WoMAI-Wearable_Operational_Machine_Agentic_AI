from datetime import datetime, timezone

from pydantic import BaseModel, Field


class SensorReadingIn(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    air_temperature_k: float
    process_temperature_k: float
    rotational_speed_rpm: int
    tool_wear_min: float


class SensorReadingBatchIn(BaseModel):
    readings: list[SensorReadingIn]


class SensorReadingOut(BaseModel):
    id: str
    run_id: str | None
    reading_timestamp: datetime
    air_temperature_k: float
    process_temperature_k: float
    rotational_speed_rpm: int
    tool_wear_min: float
    machine_failure: bool | None
    input_source: str

    model_config = {"from_attributes": True}


class SensorRunOut(BaseModel):
    id: str
    run_label: str
    start_timestamp: datetime
    end_timestamp: datetime
    sample_count: int
    failure_count: int
    is_closed: bool

    model_config = {"from_attributes": True}


class SensorReadingSubmitResponseOut(BaseModel):
    reading: SensorReadingOut
    run: SensorRunOut


class SensorHistoryPointOut(BaseModel):
    timestamp: datetime
    air_temperature_k: float
    process_temperature_k: float
    rotational_speed_rpm: int
    tool_wear_min: float
    # True kalau reading ini di luar rentang wajar (IQR bounds dari data training
    # model, best_performance_log.json) pada SALAH SATU parameter yang punya
    # bounds — dipakai frontend untuk menandai titik merah di line chart.
    is_anomaly: bool


class SensorParamStatsOut(BaseModel):
    min: float | None
    max: float | None
    avg: float | None
    current: float | None


class SensorHistoryOut(BaseModel):
    run_label: str | None
    points: list[SensorHistoryPointOut]
    air_temperature_k: SensorParamStatsOut
    process_temperature_k: SensorParamStatsOut
    rotational_speed_rpm: SensorParamStatsOut
    tool_wear_min: SensorParamStatsOut
