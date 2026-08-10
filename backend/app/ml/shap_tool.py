"""SHAP — Section 6.7, adapted untuk pipeline 11-fitur (lihat predictor.py untuk
alasan deviasi dari contoh rancangan yang cuma pakai 4 fitur mentah).

`model` di sini adalah RandomForestClassifier di dalam pipeline (langkah 'clf'),
dipanggil pada representasi SUDAH di-scale (StandardScaler step) supaya
TreeExplainer bekerja pada domain numerik yang sama dengan training. background_data
juga harus sudah melewati add_base_features+apply_risk_features+scaler.transform
sebelum masuk sini — build_background_data() di bawah menyiapkan itu.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
import shap

from app.ml.predictor import RAW_TO_MODEL_COL, build_model_features, get_model_bundle

_explainer_cache: dict[int, "shap.TreeExplainer"] = {}

# Section revisi rancangan.txt: SHAP hanya boleh menampilkan kontribusi dari
# fitur SENSOR MENTAH (bukan fitur turunan seperti temp_diff/tool_wear_rate/
# heat_dissipation_risk, dst — nama variabel Python itu tidak berarti apa-apa
# bagi user, dan kontribusi SHAP-nya sudah otomatis "diserap" ke fitur mentah
# yang mereka berasal dari lewat feature engineering; menampilkan keduanya
# double-counts the same underlying signal for the reader). RAW_TO_MODEL_COL
# nilainya sudah nama kolom asli dataset ("Air temperature K", dst) — dipakai
# apa adanya sebagai display name yang manusiawi, tidak perlu mapping baru.
DISPLAY_FEATURE_NAMES = set(RAW_TO_MODEL_COL.values())


def build_background_data(historical_df: pd.DataFrame, sample_size: int = 200) -> pd.DataFrame:
    """historical_df: DataFrame mentah dengan kolom RAW_FEATURE_ORDER (snake_case).
    Returns DataFrame fitur penuh (feature_cols model) untuk dipakai sbg SHAP baseline.
    """
    bundle = get_model_bundle()
    df = historical_df.sample(n=min(sample_size, len(historical_df)), random_state=42) if len(historical_df) > sample_size else historical_df
    rows = []
    for _, r in df.iterrows():
        reading = {
            "air_temperature_k": float(r["air_temperature_k"]),
            "process_temperature_k": float(r["process_temperature_k"]),
            "rotational_speed_rpm": float(r["rotational_speed_rpm"]),
            "tool_wear_min": float(r["tool_wear_min"]),
        }
        rows.append(build_model_features(reading).iloc[0])
    return pd.DataFrame(rows)[bundle.feature_cols].reset_index(drop=True)


def _get_explainer(clf, background_scaled: np.ndarray):
    model_id = id(clf)
    if model_id not in _explainer_cache:
        _explainer_cache[model_id] = shap.TreeExplainer(clf, background_scaled)
    return _explainer_cache[model_id]


def explain_failure_shap(feature_row: dict, background_data: pd.DataFrame) -> dict:
    """Tool function (dipanggil manual sekarang, jadi tool agent LangGraph nanti).

    Args:
        feature_row: dict snake_case {"air_temperature_k", "process_temperature_k",
            "rotational_speed_rpm", "tool_wear_min"} — fitur MENTAH (belum di-derive).
        background_data: sample data historis MENTAH (kolom snake_case sama), dipakai
            sbg baseline TreeExplainer setelah melewati feature engineering + scaling
            yang identik dengan training.

    Returns:
        {"base_value": float, "features": [{"feature_name", "value", "shap_value", "rank"}, ...]}
    """
    bundle = get_model_bundle()
    pipeline = bundle.pipeline
    scaler = pipeline.named_steps["scaler"]
    clf = pipeline.named_steps["clf"]

    x_full = build_model_features(feature_row)  # 1 baris, 11 kolom, urutan feature_cols
    x_scaled = scaler.transform(x_full)

    background_full = build_background_data(background_data)
    background_scaled = scaler.transform(background_full)

    explainer = _get_explainer(clf, background_scaled)
    shap_values = explainer.shap_values(x_scaled)

    # RandomForestClassifier binary -> shap_values is list[class0, class1] or 3D array
    # depending on shap version; normalize to a 1D array for the positive (failure) class.
    if isinstance(shap_values, list):
        values = np.asarray(shap_values[1])[0]
        expected_value = explainer.expected_value[1]
    else:
        arr = np.asarray(shap_values)
        if arr.ndim == 3:
            values = arr[0, :, 1]
            expected_value = (
                explainer.expected_value[1]
                if isinstance(explainer.expected_value, (list, np.ndarray))
                else explainer.expected_value
            )
        else:
            values = arr[0]
            expected_value = explainer.expected_value

    raw_only = [
        (f, v, s)
        for f, v, s in zip(bundle.feature_cols, x_full.iloc[0].tolist(), np.asarray(values).tolist())
        if f in DISPLAY_FEATURE_NAMES
    ]
    ranked = sorted(raw_only, key=lambda t: abs(t[2]), reverse=True)
    return {
        "base_value": float(expected_value),
        "features": [
            {"feature_name": f, "value": float(v), "shap_value": float(s), "rank": i + 1}
            for i, (f, v, s) in enumerate(ranked)
        ],
    }
