"""Prediksi horizon — "Probability Failure in +10 Minute" (rancangan.txt
Section 5). Model TERPISAH dari predictor_clasification.py: menjawab
pertanyaan berbeda ("akan gagal dalam 10 menit ke depan?", bukan "sedang
gagal sekarang?").

Model: backend/saved/horizon/horizon_model.pkl — XGBoost, dilatih di
model_horizon_kedua.ipynb §2.6 (lihat guide_model.md di folder yang sama).
Bundle-nya dict: {"model": XGBClassifier, "features": [...4 kolom...],
"threshold": float, "horizon_minutes": int, ...}.

4 fitur MENTAH saja (air_temp_K, proc_temp_K, rpm, tool_wear_min) — TIDAK ada
feature engineering, TIDAK ada scaling ("scaling: tidak ada; XGBoost tidak
butuh scaling" — bundle['preprocessing']). Preprocessing yang didokumentasikan
di bundle (cycle/delta_min/t_min/sort) hanya dipakai untuk menyusun TARGET
saat training (window waktu ke depan per tool-cycle) — tidak relevan untuk
inference satu baris baru secara real-time, karena baris itu belum punya
"masa depan" untuk dihitung mundur.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache

import joblib
import pandas as pd

from app.config import settings

RAW_FEATURE_ORDER = ["air_temperature_k", "process_temperature_k", "rotational_speed_rpm", "tool_wear_min"]

RAW_TO_MODEL_COL = {
    "air_temperature_k": "air_temp_K",
    "process_temperature_k": "proc_temp_K",
    "rotational_speed_rpm": "rpm",
    "tool_wear_min": "tool_wear_min",
}


@dataclass
class HorizonModelBundle:
    model: object
    features: list[str]
    threshold: float
    horizon_minutes: int
    model_version: str


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


@lru_cache(maxsize=1)
def _load_model_bundle() -> HorizonModelBundle:
    raw = joblib.load(settings.ML_HORIZON_MODEL_PATH)
    model_version = f"horizon-{_file_hash(settings.ML_HORIZON_MODEL_PATH)}"
    return HorizonModelBundle(
        model=raw["model"],
        features=raw["features"],
        threshold=float(raw["threshold"]),
        horizon_minutes=int(raw["horizon_minutes"]),
        model_version=model_version,
    )


@dataclass
class HorizonResult:
    label: bool
    probability: float
    model_version: str
    threshold: float
    horizon_minutes: int


def predict_failure_horizon(reading: dict) -> HorizonResult:
    """reading: dict snake_case RAW_FEATURE_ORDER. Fitur mentah langsung,
    tanpa scaling/feature engineering (lihat docstring modul)."""
    bundle = _load_model_bundle()
    row = {RAW_TO_MODEL_COL[f]: reading[f] for f in RAW_FEATURE_ORDER}
    x = pd.DataFrame([row])[bundle.features]
    proba = float(bundle.model.predict_proba(x)[0][1])
    label = bool(proba >= bundle.threshold)
    return HorizonResult(
        label=label,
        probability=proba,
        model_version=bundle.model_version,
        threshold=bundle.threshold,
        horizon_minutes=bundle.horizon_minutes,
    )


def get_model_bundle() -> HorizonModelBundle:
    return _load_model_bundle()
