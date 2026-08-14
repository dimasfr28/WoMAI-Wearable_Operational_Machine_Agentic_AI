"""Compose laporan akhir — Section 6.10 step 5, generate_final_report()."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from app.config import settings
from app.llm.groq_client import chat, chat_json

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


@dataclass
class EarlyWarningContext:
    """Konteks untuk kartu Early Warning (frontend /report page) — bagian "AI
    Diagnosis" & "Recommended Action". feature/current_value/target_value pada
    recommended action DIHITUNG di routes_report.py (dari worst_case_delta),
    bukan oleh LLM — di sini LLM cuma menulis prosa (why/expected_impact),
    supaya angka tetap dapat dipercaya."""

    predicted_label: bool
    probability: float
    top_feature_name: str
    recommended_feature: str | None
    recommended_current: float | None
    recommended_target: float | None


EARLY_WARNING_PROMPT = """Anda adalah asisten predictive maintenance untuk mesin CNC Haas.
Balas HANYA JSON dengan skema persis ini (tanpa teks lain):
{{
  "ai_explanation": "<1-2 kalimat Bahasa Indonesia menjelaskan mengapa prediksi ini terjadi, sebutkan fitur paling berpengaruh>",
  "why": "<1 kalimat Bahasa Indonesia menjelaskan mengapa penyesuaian yang disarankan akan membantu, atau string kosong kalau tidak ada rekomendasi>",
  "expected_impact": "<1 kalimat singkat Bahasa Indonesia dampak yang diharapkan dari penyesuaian, atau string kosong kalau tidak ada rekomendasi>"
}}

Data:
- Prediksi: {label_text} (probabilitas kegagalan {probability_pct}%)
- Fitur paling berpengaruh: {top_feature}
- Rekomendasi penyesuaian: {recommendation_text}
"""


def generate_early_warning_narrative(context: EarlyWarningContext) -> dict:
    label_text = "Kegagalan diprediksi" if context.predicted_label else "Kondisi normal, tidak ada kegagalan diprediksi"
    probability_pct = round(context.probability * 100, 1)
    if context.recommended_feature is not None:
        recommendation_text = (
            f"{context.recommended_feature}: dari {context.recommended_current} "
            f"menuju {context.recommended_target}"
        )
    else:
        recommendation_text = "(tidak ada rekomendasi — data historis belum cukup)"

    prompt = EARLY_WARNING_PROMPT.format(
        label_text=label_text,
        probability_pct=probability_pct,
        top_feature=context.top_feature_name,
        recommendation_text=recommendation_text,
    )
    try:
        raw = chat_json([{"role": "user", "content": prompt}], model=settings.GROQ_MODEL)
        data = json.loads(raw)
        return {
            "ai_explanation": data.get("ai_explanation") or "",
            "why": data.get("why") or "",
            "expected_impact": data.get("expected_impact") or "",
        }
    except Exception:
        logger.exception("generate_early_warning_narrative: Groq call failed")
        return {
            "ai_explanation": f"{context.top_feature_name} adalah faktor paling berpengaruh terhadap prediksi ini.",
            "why": "",
            "expected_impact": "",
        }
