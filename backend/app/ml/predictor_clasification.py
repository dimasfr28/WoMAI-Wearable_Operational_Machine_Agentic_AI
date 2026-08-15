"""Prediksi failure — model klasifikasi baru (rancangan.txt Section 5, "Failure
Clasification"). Menggantikan predictor.py's best_model.pkl (RandomForest,
11 fitur turunan lama), yang sudah dihapus dan tidak dipakai lagi.

Model: backend/saved/clasification/clasification_model.pkl — XGBoost·rec,
dilatih ulang di replikasi_ai4i2020.ipynb (lihat guide_model.md di folder yang
sama). Bundle-nya adalah dict, bukan bare estimator:
  {"pipeline": imblearn.pipeline.Pipeline, "threshold": float,
   "feature_names": [...9 kolom...], "model_name": "XGBoost·rec", ...}

9 fitur (4 mentah + 5 turunan FISIK — definisinya BEDA dari predictor.py lama,
bukan superset/subset-nya):
  air_temp_K, proc_temp_K, rpm, tool_wear_min,
  Temp_diff, Temp_ratio, Wear_x_rpm, Cooling_margin_rate, Thermal_wear_load

Pipeline sudah membungkus StandardScaler sendiri (step "scaler") — TIDAK perlu
scaling manual sebelum predict_proba(), beda dari cara shap_tool.py memakai
predictor.py lama (yang memisahkan scaler dari clf secara eksplisit untuk
TreeExplainer). Torque sengaja tidak dipakai sama sekali (lihat guide_model.md).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from app.config import settings

# Kolom mentah dari sensor_readings (snake_case) -> nama kolom model (dataset asli).
RAW_FEATURE_ORDER = ["air_temperature_k", "process_temperature_k", "rotational_speed_rpm", "tool_wear_min"]

RAW_TO_MODEL_COL = {
    "air_temperature_k": "air_temp_K",
    "process_temperature_k": "proc_temp_K",
    "rotational_speed_rpm": "rpm",
    "tool_wear_min": "tool_wear_min",
}

# feature_name (model column, "air_temp_K" dst) -> (parameter key snake_case
# dipakai frontend/schemas, label tampilan manusiawi, satuan). Shared constant
# — dipakai routes_machine.py (Early Warning) dan app/reports/report_pdf.py
# (Machine Report) supaya label parameter konsisten di kedua tempat.
PARAM_META = {
    "air_temp_K": ("air_temperature_k", "Air Temperature", "K"),
    "proc_temp_K": ("process_temperature_k", "Process Temperature", "K"),
    "rpm": ("rotational_speed_rpm", "Rotational Speed", "rpm"),
    "tool_wear_min": ("tool_wear_min", "Tool Wear", "min"),
}


def _add_derived_features(data: pd.DataFrame) -> pd.DataFrame:
    """Identik buat_fitur() di replikasi_ai4i2020.ipynb TAHAP 3 — 5 fitur turunan
    berbasis mekanisme fisik. Definisinya SENGAJA berbeda dari predictor.py
    lama's add_base_features() (nama & rumus keduanya tidak sama), jadi jangan
    disatukan/disamakan meski konsepnya mirip."""
    data = data.copy()
    data["Temp_diff"] = data["proc_temp_K"] - data["air_temp_K"]
    data["Temp_ratio"] = data["proc_temp_K"] / (data["air_temp_K"] + 1e-6)
    data["Wear_x_rpm"] = data["tool_wear_min"] * data["rpm"]
    # Cooling_margin_rate: pembuangan panas per satuan kecepatan — Temp_diff
    # relatif terhadap rpm (rpm tinggi = pendinginan konvektif lebih efektif).
    data["Cooling_margin_rate"] = data["Temp_diff"] / (data["rpm"] + 1e-6)
    data["Thermal_wear_load"] = data["Temp_diff"] * data["tool_wear_min"]
    return data


def build_model_features(reading: dict) -> pd.DataFrame:
    """reading: dict snake_case RAW_FEATURE_ORDER. Returns DataFrame satu baris,
    9 kolom, urutan sama seperti bundle['feature_names']."""
    bundle = _load_model_bundle()
    row = {RAW_TO_MODEL_COL[f]: reading[f] for f in RAW_FEATURE_ORDER}
    df = pd.DataFrame([row])
    df = _add_derived_features(df)
    return df[bundle.feature_names]


@dataclass
class ClasificationModelBundle:
    pipeline: object
    feature_names: list[str]
    threshold: float
    model_name: str
    model_version: str


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


@lru_cache(maxsize=1)
def _load_model_bundle() -> ClasificationModelBundle:
    raw = joblib.load(settings.ML_CLASIFICATION_MODEL_PATH)
    model_version = f"{raw.get('model_name', 'clasification')}-{_file_hash(settings.ML_CLASIFICATION_MODEL_PATH)}"
    return ClasificationModelBundle(
        pipeline=raw["pipeline"],
        feature_names=raw["feature_names"],
        threshold=float(raw["threshold"]),
        model_name=raw.get("model_name", "clasification"),
        model_version=model_version,
    )


@dataclass
class ClasificationResult:
    label: bool
    probability: float
    model_version: str
    threshold: float


def predict_failure(reading: dict) -> ClasificationResult:
    """reading: dict snake_case {"air_temperature_k", "process_temperature_k",
    "rotational_speed_rpm", "tool_wear_min"}. Pipeline sudah termasuk scaler —
    predict_proba() langsung dipanggil pada 9 fitur belum di-scale."""
    bundle = _load_model_bundle()
    x = build_model_features(reading)
    proba = float(bundle.pipeline.predict_proba(x)[0][1])
    label = bool(proba >= bundle.threshold)
    return ClasificationResult(
        label=label,
        probability=proba,
        model_version=bundle.model_version,
        threshold=bundle.threshold,
    )


def get_model_bundle() -> ClasificationModelBundle:
    """Exposed for shap_tool.py, yang butuh pipeline + feature_names langsung."""
    return _load_model_bundle()
