"""Content-Based Recommendation (KNN) + Worst-Case Delta — Section 6.8.

Uses the same 4 raw sensor features as the design doc (FEATURE_ORDER), operating
directly on sensor_readings history — this part of the spec did not need the
predictor.py fix since KNN similarity is defined in raw sensor-feature space, not
model-input space.
"""
from __future__ import annotations

import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from app.ml.predictor_clasification import RAW_TO_MODEL_COL

FEATURE_ORDER = ["air_temperature_k", "process_temperature_k", "rotational_speed_rpm", "tool_wear_min"]


def recommend_similar_cases(feature_row: dict, historical_df: pd.DataFrame, k: int = 5) -> dict:
    """Tool function. historical_df berisi seluruh sensor_readings berlabel
    (machine_failure IS NOT NULL), kolom FEATURE_ORDER + machine_failure.

    Returns dua kelompok neighbor (nearest failure & nearest no-failure) supaya
    agent bisa membandingkan posisi kondisi sekarang terhadap kedua kelas.
    """
    X = historical_df[FEATURE_ORDER].values
    scaler = StandardScaler().fit(X)
    X_scaled = scaler.transform(X)
    x_query = scaler.transform(pd.DataFrame([feature_row])[FEATURE_ORDER].values)

    failure_mask = historical_df["machine_failure"].astype(bool).values
    result: dict = {}
    for label, mask in [("nearest_failure", failure_mask), ("nearest_no_failure", ~failure_mask)]:
        n_available = int(mask.sum())
        if n_available == 0:
            result[label] = {"distances": [], "rows": []}
            continue
        nn = NearestNeighbors(n_neighbors=min(k, n_available)).fit(X_scaled[mask])
        dist, idx = nn.kneighbors(x_query)
        neighbors = historical_df[mask].iloc[idx[0]]
        result[label] = {
            "distances": dist[0].tolist(),
            "rows": neighbors[FEATURE_ORDER + ["machine_failure"]].to_dict(orient="records"),
        }
    return result


def worst_case_delta(feature_row: dict, historical_df: pd.DataFrame) -> dict:
    """Tool function: cari titik NO-FAILURE termirip (bukan identik) dari kondisi
    sekarang, lalu hitung selisih HANYA untuk fitur yang benar-benar berbeda sebagai
    saran penyesuaian.

    "Termirip tapi tidak sama persis" (revisi rancangan.txt): ambil beberapa
    tetangga terdekat sekaligus dan pakai yang PERTAMA dengan jarak > 0 — kalau
    tetangga #1 kebetulan identik (jarak 0, tidak ada apa pun untuk disarankan),
    lanjut ke tetangga berikutnya. k=5 dulu; kalau semuanya kebetulan identik
    (mustahil dalam praktik, hanya bisa terjadi pada dataset sintetis kecil
    dengan banyak duplikat), fallback ke apa adanya lewat `next(..., default)`.
    """
    k = min(5, int((~historical_df["machine_failure"].astype(bool)).sum()))
    nearest_group = recommend_similar_cases(feature_row, historical_df, k=k)["nearest_no_failure"]
    rows, distances = nearest_group["rows"], nearest_group["distances"]
    if not rows:
        return {"nearest_safe_point": None, "suggested_adjustments": {}}

    nearest, _dist = next(
        ((r, d) for r, d in zip(rows, distances) if d > 0),
        (rows[0], distances[0]),
    )

    # Hanya fitur yang benar-benar berbeda (setelah pembulatan 2 desimal, sesuai
    # presisi output) yang layak disebut sebagai "penyesuaian" — delta 0.00
    # bukan rekomendasi, itu noise dari perbandingan floating-point.
    deltas = {}
    for f in FEATURE_ORDER:
        delta = round(float(nearest[f]) - float(feature_row[f]), 2)  # target - current
        if delta != 0:
            deltas[RAW_TO_MODEL_COL[f]] = delta

    return {"nearest_safe_point": nearest, "suggested_adjustments": deltas}
