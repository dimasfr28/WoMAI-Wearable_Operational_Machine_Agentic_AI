"""Compose laporan akhir — Section 6.10 step 5, generate_final_report()."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.config import settings
from app.llm.groq_client import chat

logger = logging.getLogger(__name__)


@dataclass
class FinalReportContext:
    prediction: dict
    shap_top_features: list
    worst_case_delta: dict
    similar_cases: dict
    root_cause_answer: str | None = None
    part_price: list = field(default_factory=list)


FINAL_REPORT_PROMPT = """Anda adalah asisten predictive maintenance untuk mesin CNC Haas.
Susun laporan ringkas dalam Bahasa Indonesia (format markdown) untuk engineer, berdasarkan
data berikut:

## Hasil Prediksi
{prediction}

## Fitur Paling Berpengaruh (SHAP)
{shap_top_features}

## Saran Penyesuaian (Worst-Case Delta)
{worst_case_delta}

## Kasus Serupa (KNN)
{similar_cases}

## Analisis Root Cause
{root_cause}

## Estimasi Harga Part (hasil pencarian di platform e-commerce: Shopee/Tokopedia/Lazada/Alibaba/dll)
{part_price}

Buat laporan singkat (maks 300 kata) dengan struktur:
1. Ringkasan kondisi & risiko
2. Faktor utama penyebab risiko
3. Rekomendasi tindakan konkret
4. Estimasi biaya — HANYA gunakan angka dari data "Estimasi Harga Part" di atas (hasil
   pencarian e-commerce), JANGAN mengarang atau menyebut harga dari sumber lain (manual
   servis, forum, dll). Kalau data kosong/tidak ada harga ditemukan, katakan dengan jelas
   bahwa harga belum tersedia dari platform e-commerce dan sarankan pengecekan manual.
"""


def generate_final_report(context: FinalReportContext) -> str:
    prompt = FINAL_REPORT_PROMPT.format(
        prediction=context.prediction,
        shap_top_features=context.shap_top_features,
        worst_case_delta=context.worst_case_delta,
        similar_cases=context.similar_cases,
        root_cause=context.root_cause_answer or "(tidak dijalankan — prediksi tidak menunjukkan failure)",
        part_price=context.part_price or "(tidak ada data harga part)",
    )
    try:
        return chat([{"role": "user", "content": prompt}], model=settings.GROQ_MODEL, temperature=0.3)
    except Exception:
        logger.exception("generate_final_report: Groq call failed")
        return (
            "**Laporan otomatis tidak dapat dibuat** (layanan LLM tidak tersedia saat ini). "
            "Data prediksi, SHAP, dan rekomendasi tetap tersedia di atas untuk ditinjau manual."
        )
