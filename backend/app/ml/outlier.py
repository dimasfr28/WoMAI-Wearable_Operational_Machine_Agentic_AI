"""IQR outlier detection per RUN ID (rancangan.txt, AI Early Warning section):
"lakukan outlier detection menggunakan IQR untuk setiap RUN ID" — bounds
dihitung on-the-fly dari readings DALAM satu run, bukan dari bound statis
global training (yang tidak ada lagi sejak model lama/best_performance_log.json
dihapus — model klasifikasi baru tidak menyertakan bounds tersimpan seperti itu).

Satu run bisa berisi sedikit reading di awal (mis. baru 1-2 baris) — IQR
butuh minimal beberapa titik data untuk bermakna secara statistik; di bawah
MIN_SAMPLES_FOR_IQR, deteksi outlier di-skip (tidak ada cukup data untuk
menyimpulkan apa pun sebagai "outlier" terhadap dirinya sendiri).
"""
from __future__ import annotations

from dataclasses import dataclass

MIN_SAMPLES_FOR_IQR = 4


@dataclass
class IqrBounds:
    lower: float
    upper: float


def compute_iqr_bounds(values: list[float]) -> IqrBounds | None:
    """Bounds Tukey standar: Q1 - 1.5*IQR, Q3 + 1.5*IQR. Returns None kalau
    datanya terlalu sedikit untuk kuartil yang bermakna."""
    n = len(values)
    if n < MIN_SAMPLES_FOR_IQR:
        return None

    sorted_vals = sorted(values)

    def _percentile(data: list[float], pct: float) -> float:
        idx = pct * (len(data) - 1)
        lo, hi = int(idx), min(int(idx) + 1, len(data) - 1)
        frac = idx - lo
        return data[lo] + (data[hi] - data[lo]) * frac

    q1 = _percentile(sorted_vals, 0.25)
    q3 = _percentile(sorted_vals, 0.75)
    iqr = q3 - q1
    return IqrBounds(lower=q1 - 1.5 * iqr, upper=q3 + 1.5 * iqr)


@dataclass
class RunIqrBounds:
    """Bounds IQR per fitur, dihitung dari seluruh reading dalam SATU run."""

    air_temperature_k: IqrBounds | None
    process_temperature_k: IqrBounds | None
    rotational_speed_rpm: IqrBounds | None
    tool_wear_min: IqrBounds | None


def compute_run_iqr_bounds(readings: list[dict]) -> RunIqrBounds:
    """readings: list of dict dengan key air_temperature_k/process_temperature_k/
    rotational_speed_rpm/tool_wear_min (snake_case, seperti dari SensorReading)."""
    return RunIqrBounds(
        air_temperature_k=compute_iqr_bounds([float(r["air_temperature_k"]) for r in readings]),
        process_temperature_k=compute_iqr_bounds([float(r["process_temperature_k"]) for r in readings]),
        rotational_speed_rpm=compute_iqr_bounds([float(r["rotational_speed_rpm"]) for r in readings]),
        tool_wear_min=compute_iqr_bounds([float(r["tool_wear_min"]) for r in readings]),
    )


def is_value_outlier(value: float, bounds: IqrBounds | None) -> bool:
    if bounds is None:
        return False
    return value < bounds.lower or value > bounds.upper
