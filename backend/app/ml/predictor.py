"""Prediksi Failure — Section 6.6, DIPERBAIKI dari contoh rancangan.

DEVIASI WAJIB dari RANCANGAN_SISTEM.md Section 6.6:
  Rancangan menulis predictor.py sebagai contoh yang disederhanakan: load
  `best_model.pkl` sebagai bare estimator dan panggil `model.predict_proba()`
  langsung dengan 4 fitur mentah (FEATURE_ORDER).

  Ini keliru untuk model yang benar-benar dilatih di
  predictive_maintenance_full.ipynb:
    1. `best_model.pkl` bukan bare pipeline, melainkan sebuah dict:
       {"pipeline": sklearn Pipeline, "optimal_threshold": float,
        "feature_cols": [...11 kolom...], "best_model": "RandomForest", ...}
    2. Pipeline itu di-fit dengan 11 kolom (4 mentah + 7 turunan), BUKAN 4 kolom
       mentah saja: lihat code/modul/explore_fitur.py -> add_base_features()
       menambah temp_diff/temp_ratio/tool_wear_rate/rpm_wear_interaction/
       temp_wear_interaction, lalu apply_risk_features() (dengan lower_bound/
       upper_bound dari IQR TRAIN split, disimpan di
       best_performance_log.json['bounds']) menambah heat_dissipation_risk
       dan tool_wear_risk.
    3. Threshold keputusan optimalnya BUKAN 0.5 hardcoded, melainkan
       `optimal_threshold` (0.503333) dari run terakhir di
       best_performance_log.json.

  Kalau predictor dipanggil persis seperti contoh rancangan (4 kolom mentah
  langsung ke `model.predict_proba()`), scikit-learn akan melempar
  ValueError karena StandardScaler di dalam pipeline di-fit dengan 11 fitur
  dan menerima jumlah kolom yang salah. Implementasi di bawah ini menerapkan
  add_base_features() + apply_risk_features() (dengan bounds yang sama persis
  dipakai saat training) sebelum predict_proba(), sesuai catatan wajib di
  instruksi tugas.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache

import joblib
import pandas as pd

from app.config import settings

# Kolom mentah yang datang dari sensor_readings / form input — urutan ini
# dipakai untuk membangun DataFrame awal sebelum feature engineering.
RAW_FEATURE_ORDER = ["air_temperature_k", "process_temperature_k", "rotational_speed_rpm", "tool_wear_min"]

# Mapping nama kolom snake_case (dipakai internal API/DB) <-> nama kolom asli
# dataset (dipakai model & explore_fitur.py, ada spasi + kapital).
RAW_TO_MODEL_COL = {
    "air_temperature_k": "Air temperature K",
    "process_temperature_k": "Process temperature K",
    "rotational_speed_rpm": "Rotational speed rpm",
    "tool_wear_min": "Tool wear min",
}


def _add_base_features(data: pd.DataFrame) -> pd.DataFrame:
    """Identik add_base_features() di code/modul/explore_fitur.py."""
    data = data.copy()
    data["temp_diff"] = data["Process temperature K"] - data["Air temperature K"]
    data["temp_ratio"] = data["Process temperature K"] / (data["Air temperature K"] + 1e-6)
    data["tool_wear_rate"] = data["Tool wear min"] / (data["Rotational speed rpm"] + 1e-6)
    data["rpm_wear_interaction"] = data["Rotational speed rpm"] * data["Tool wear min"]
    data["temp_wear_interaction"] = data["temp_diff"] * data["Tool wear min"]
    return data


def _apply_risk_features(data: pd.DataFrame, lower_bound: dict, upper_bound: dict) -> pd.DataFrame:
    """Identik apply_risk_features() di code/modul/explore_fitur.py."""
    import numpy as np

    data = data.copy()
    temp_outlier = (data["temp_diff"] < lower_bound["temp_diff"]) | (data["temp_diff"] > upper_bound["temp_diff"])
    rpm_outlier = (data["Rotational speed rpm"] < lower_bound["Rotational speed rpm"]) | (
        data["Rotational speed rpm"] > upper_bound["Rotational speed rpm"]
    )
    data["heat_dissipation_risk"] = (temp_outlier & rpm_outlier).astype(np.int8)
    data["tool_wear_risk"] = (
        (data["Tool wear min"] < lower_bound["Tool wear min"]) | (data["Tool wear min"] > upper_bound["Tool wear min"])
    ).astype(np.int8)
    return data


def build_model_features(reading: dict) -> pd.DataFrame:
    """reading: dict dengan key snake_case RAW_FEATURE_ORDER (mis. dari sensor_readings).
    Returns DataFrame satu baris dengan seluruh 11 feature_cols model, dalam urutan
    yang sama seperti saat training (explore_train_test -> add_base_features -> apply_risk_features).
    """
    bundle = _load_model_bundle()
    row = {RAW_TO_MODEL_COL[f]: reading[f] for f in RAW_FEATURE_ORDER}
    df = pd.DataFrame([row])
    df = _add_base_features(df)
    df = _apply_risk_features(df, bundle.lower_bound, bundle.upper_bound)
    return df[bundle.feature_cols]


@dataclass
class ModelBundle:
    pipeline: object
    feature_cols: list[str]
    optimal_threshold: float
    lower_bound: dict
    upper_bound: dict
    model_version: str


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


@lru_cache(maxsize=1)
def _load_model_bundle() -> ModelBundle:
    raw = joblib.load(settings.ML_MODEL_PATH)
    pipeline = raw["pipeline"]
    feature_cols = raw["feature_cols"]
    optimal_threshold = float(raw["optimal_threshold"])

    perf_log_path = settings.ML_PERFORMANCE_LOG_PATH
    lower_bound: dict = {}
    upper_bound: dict = {}
    if os.path.exists(perf_log_path):
        with open(perf_log_path, encoding="utf-8") as f:
            log = json.load(f)
        # Ambil run TERAKHIR (paling baru) sesuai instruksi tugas.
        last_run = log[-1] if isinstance(log, list) else log
        bounds = last_run.get("bounds", {})
        lower_bound = bounds.get("lower", {})
        upper_bound = bounds.get("upper", {})

    model_version = f"{os.path.basename(settings.ML_MODEL_PATH)}-{_file_hash(settings.ML_MODEL_PATH)}"

    return ModelBundle(
        pipeline=pipeline,
        feature_cols=feature_cols,
        optimal_threshold=optimal_threshold,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        model_version=model_version,
    )


@dataclass
class PredictionResult:
    label: bool
    probability: float
    model_version: str
    threshold: float


def predict_failure(reading: dict) -> PredictionResult:
    """reading: dict snake_case {"air_temperature_k", "process_temperature_k",
    "rotational_speed_rpm", "tool_wear_min"}. Returns label/probability using the
    FULL 11-feature pipeline + the model's own optimal_threshold (not a hardcoded 0.5).
    """
    bundle = _load_model_bundle()
    x = build_model_features(reading)
    proba = float(bundle.pipeline.predict_proba(x)[0][1])
    label = bool(proba >= bundle.optimal_threshold)
    return PredictionResult(
        label=label,
        probability=proba,
        model_version=bundle.model_version,
        threshold=bundle.optimal_threshold,
    )


def get_model_bundle() -> ModelBundle:
    """Exposed for shap_tool.py / knn_tool.py which need pipeline + feature_cols directly."""
    return _load_model_bundle()
