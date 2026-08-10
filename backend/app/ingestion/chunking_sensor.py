"""Sensor data -> knowledgebase chunking.

Two code paths, both following the same narrative-chunk pattern as
knowledgebase.ipynb cell 12 (`build_run_chunk` / `segment_runs_by_tool_wear`):

1. `segment_runs_by_tool_wear` + `build_batch_run_chunk` — used once to seed the
   knowledgebase from the historical `dataset.csv` (batch import), producing chunks
   with the exact schema of the "dataset" doc in chunks.json.
2. `build_run_chunk` (Section 6.4 of RANCANGAN_SISTEM.md) — used at runtime every
   time a `sensor_runs` row transitions to `is_closed=True`, so the knowledgebase
   is always populated with completed real-time runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

DATASET_FIELDS = [
    "air_temperature_k",
    "process_temperature_k",
    "rotational_speed_rpm",
    "tool_wear_min",
    "machine_failure",
]


# ---------------------------------------------------------------------------
# Batch CSV segmentation (knowledgebase.ipynb cell 12) — used for one-off seeding
# ---------------------------------------------------------------------------


def segment_runs_by_tool_wear(rows: list[dict]) -> list[tuple[int, int]]:
    """Segmentasi baris jadi list (start, end) per run berdasarkan reset 'Tool wear min'.
    Run baru dimulai setiap kali nilai turun dibanding baris sebelumnya."""
    tool_wear = [float(r["Tool wear min"]) for r in rows]
    runs = []
    start = 0
    for i in range(1, len(tool_wear)):
        if tool_wear[i] < tool_wear[i - 1]:
            runs.append((start, i))
            start = i
    runs.append((start, len(tool_wear)))
    return runs


def build_batch_run_chunk(run_idx: int, start: int, end: int, rows: list[dict], doc_name: str) -> dict:
    """Identik build_run_chunk() notebook cell 12 — dipakai untuk seeding dataset.csv historis."""
    run_rows = rows[start:end]
    data_points = [
        {
            "air_temperature_k": float(r["Air temperature K"]),
            "process_temperature_k": float(r["Process temperature K"]),
            "rotational_speed_rpm": int(float(r["Rotational speed rpm"])),
            "tool_wear_min": float(r["Tool wear min"]),
            "machine_failure": int(r["Machine failure"]),
        }
        for r in run_rows
    ]
    failure_count = sum(dp["machine_failure"] for dp in data_points)
    summary = (
        f"Percobaan (run) #{run_idx}: {len(data_points)} titik data, "
        f"tool wear {data_points[0]['tool_wear_min']:.0f} - {data_points[-1]['tool_wear_min']:.0f} menit, "
        f"suhu udara {data_points[0]['air_temperature_k']:.1f}K - {data_points[-1]['air_temperature_k']:.1f}K, "
        f"{'terjadi ' + str(failure_count) + ' machine failure' if failure_count else 'tidak ada machine failure'}."
    )
    row_strs = [
        ", ".join(f"{field}: {dp[field]}" for field in DATASET_FIELDS)
        for dp in data_points
    ]
    content = summary + "\n\n" + "; ".join(row_strs)
    return {
        "doc": doc_name,
        "machine_type": "Haas",
        "heading_1": "Predictive Maintenance Dataset",
        "heading_2": f"Run {run_idx}",
        "content": content,
    }


def build_chunks_from_dataset_rows(rows: list[dict], doc_name: str = "dataset") -> list[dict]:
    """Full pipeline: segment dataset.csv rows into runs, build one chunk per run."""
    runs = segment_runs_by_tool_wear(rows)
    return [
        build_batch_run_chunk(i + 1, start, end, rows, doc_name=doc_name)
        for i, (start, end) in enumerate(runs)
    ]


# ---------------------------------------------------------------------------
# Section 6.3 / 6.4 — real-time run object (protocol-typed) for build_run_chunk
# ---------------------------------------------------------------------------


@dataclass
class RunLike:
    run_label: str


@dataclass
class ReadingLike:
    air_temperature_k: float
    process_temperature_k: float
    rotational_speed_rpm: int
    tool_wear_min: float
    machine_failure: bool | None


def build_run_chunk(run: RunLike, readings: Iterable[ReadingLike]) -> dict:
    """Section 6.4 — dipanggil setiap kali sebuah run real-time ditutup
    (is_closed berubah jadi True), supaya knowledgebase selalu berisi run
    yang sudah lengkap. Sama persis dengan RANCANGAN_SISTEM.md Section 6.4.
    """
    readings = list(readings)
    failure_count = sum(1 for r in readings if r.machine_failure)
    summary = (
        f"Percobaan (run) {run.run_label}: {len(readings)} titik data, "
        f"tool wear {readings[0].tool_wear_min:.0f} - {readings[-1].tool_wear_min:.0f} menit, "
        f"suhu udara {readings[0].air_temperature_k:.1f}K - {readings[-1].air_temperature_k:.1f}K, "
        f"{'terjadi ' + str(failure_count) + ' machine failure' if failure_count else 'tidak ada machine failure'}."
    )
    row_strs = [
        f"air_temperature_k:{r.air_temperature_k}, process_temperature_k:{r.process_temperature_k}, "
        f"rotational_speed_rpm:{r.rotational_speed_rpm}, tool_wear_min:{r.tool_wear_min}, "
        f"machine_failure:{int(r.machine_failure or False)}"
        for r in readings
    ]
    content = summary + "\n\n" + "; ".join(row_strs)
    return {
        "doc": "dataset_realtime",
        "machine_type": "Haas",
        "heading_1": "Predictive Maintenance Dataset (Real-time)",
        "heading_2": run.run_label,
        "content": content,
    }
