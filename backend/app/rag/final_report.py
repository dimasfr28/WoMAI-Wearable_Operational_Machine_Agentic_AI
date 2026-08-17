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


FINAL_REPORT_PROMPT = """You are a predictive maintenance assistant for CNC machines.
Write a concise report in English (markdown format) for an engineer, based on the data below.

## Prediction Result
{prediction}

## Top Contributing Features (SHAP)
{shap_top_features}

## Suggested Adjustment (Worst-Case Delta)
{worst_case_delta}

## Similar Cases (KNN)
{similar_cases}

## Root Cause Analysis
{root_cause}

## Estimated Part Cost (from e-commerce search: Shopee/Tokopedia/Lazada/Alibaba/etc.)
{part_price}

Write a short report (max 300 words) with this structure:
1. Condition & risk summary
2. Main factors driving the risk
3. Concrete recommended actions
4. Cost estimate — use ONLY the figures from the "Estimated Part Cost" data above (e-commerce
   search results); do not invent or cite prices from any other source (service manual, forum,
   etc.). If that data is empty/no price was found, state plainly that no e-commerce price is
   available yet and recommend a manual check.

CITATION RULE: if "Root Cause Analysis" above contains citations in "(Source Name)" format,
preserve them when you restate a cited claim — do not drop or paraphrase away a citation, and
do not invent a citation that was not present in the source data.

DIRECTNESS RULE: write direct, definitive statements grounded in the data above. Do not hedge
with vague filler words such as "maybe", "perhaps", "possibly", "it seems", or "it might be" —
state what the data supports plainly.
"""


def generate_final_report(context: FinalReportContext) -> str:
    prompt = FINAL_REPORT_PROMPT.format(
        prediction=context.prediction,
        shap_top_features=context.shap_top_features,
        worst_case_delta=context.worst_case_delta,
        similar_cases=context.similar_cases,
        root_cause=context.root_cause_answer or "(not run — prediction did not indicate a failure)",
        part_price=context.part_price or "(no part price data)",
    )
    try:
        return chat([{"role": "user", "content": prompt}], model=settings.GROQ_MODEL, temperature=0.3)
    except Exception:
        logger.exception("generate_final_report: Groq call failed")
        return (
            "**Automatic report generation is unavailable** (LLM service unreachable right now). "
            "Prediction, SHAP, and recommendation data are still available above for manual review."
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


EARLY_WARNING_PROMPT = """You are a predictive maintenance assistant for CNC machines.
Reply ONLY in JSON with exactly this schema (no other text):
{{
  "ai_explanation": "<1-2 sentences in English explaining why this prediction occurred, naming the top contributing feature>",
  "why": "<1 sentence in English explaining why the suggested adjustment would help, or an empty string if there is no recommendation>",
  "expected_impact": "<1 short sentence in English on the expected impact of the adjustment, or an empty string if there is no recommendation>",
  "cause_analysis": "<ONLY fill this if the prediction below is a NORMAL condition (not a failure): one short sentence stating the machine is currently within normal operating parameters, referencing the top contributing feature in GENERAL terms only. Do NOT name any specific machine part or component (e.g. do not say "spindle bearing", "servo motor", "coolant pump") — there is no diagnosed fault to attribute to a part. If the prediction below IS a failure, reply with an empty string here instead — a separate, real root-cause analysis covers that case.>"
}}

Write direct, definitive statements grounded in the data below. Do not hedge with vague filler
words such as "maybe", "perhaps", "possibly", "it seems", or "it might be".

Data:
- Prediction: {label_text} (failure probability {probability_pct}%)
- Top contributing feature: {top_feature}
- Suggested adjustment: {recommendation_text}
"""


def generate_early_warning_narrative(context: EarlyWarningContext) -> dict:
    label_text = "Failure predicted" if context.predicted_label else "Normal condition, no failure predicted"
    probability_pct = round(context.probability * 100, 1)
    if context.recommended_feature is not None:
        recommendation_text = (
            f"{context.recommended_feature}: from {context.recommended_current} "
            f"to {context.recommended_target}"
        )
    else:
        recommendation_text = "(no recommendation — not enough historical data yet)"

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
            "cause_analysis": data.get("cause_analysis") or "",
        }
    except Exception:
        logger.exception("generate_early_warning_narrative: Groq call failed")
        return {
            "ai_explanation": f"{context.top_feature_name} is the top contributing factor to this prediction.",
            "why": "",
            "expected_impact": "",
            "cause_analysis": (
                "" if context.predicted_label
                else f"Current readings are within normal operating parameters; {context.top_feature_name} shows no abnormal pattern."
            ),
        }


SUGGESTION_GENERAL_PROMPT = """You are a predictive maintenance assistant for CNC machines.
Turn the technical condition below into ONE concise, actionable suggestion sentence in English,
WITHOUT stating raw numeric sensor values (e.g. do NOT write "313.5 K" or "230 minutes") — use a
GENERAL term for the variable (e.g. "heat", "rotational speed", "tool wear/operating time"), and
state the direction clearly (increase or decrease).

Write a direct, definitive statement. Do not hedge with vague filler words such as "maybe",
"perhaps", "possibly", or "it might help".

Variable to adjust: {general_term}
Adjustment direction: {direction}

Reply with ONLY the one-sentence suggestion, no additional explanation.
"""


def generate_suggestion_general(feature_name: str, direction: str) -> str:
    """"Suggestions for Improvement LLM" (rancangan.txt Section 5, "AI
    Explanation" panel) — mengadaptasi pola query-generation
    (generate_search_queries() di crag_graph.py, yang juga menerjemahkan
    fitur mentah jadi istilah general via LLM) untuk membuat kalimat saran,
    bukan query pencarian. `feature_name`: nama kolom model (mis.
    "tool_wear_min", lihat predictor_clasification.py's RAW_TO_MODEL_COL).
    `direction`: "increase"/"decrease", diturunkan dari tanda worst_case_delta
    (KNN) oleh caller — LLM TIDAK menilai sendiri arah over/under, hanya
    menuliskannya jadi kalimat."""
    from app.rag.crag_graph import _SHAP_FEATURE_TO_GENERAL_TERM

    general_term = _SHAP_FEATURE_TO_GENERAL_TERM.get(feature_name, feature_name)
    prompt = SUGGESTION_GENERAL_PROMPT.format(general_term=general_term, direction=direction)
    try:
        return chat([{"role": "user", "content": prompt}], model=settings.GROQ_MODEL, temperature=0.2).strip()
    except Exception:
        logger.exception("generate_suggestion_general: Groq call failed")
        verb = "Increase" if direction == "increase" else "Decrease"
        return f"{verb} {general_term} toward a safer operating condition."


@dataclass
class WhatIfContext:
    """Konteks untuk narasi perbandingan chatbot what-if (Task 43) -- SELALU
    membandingkan skenario hipotetis terhadap kondisi mesin NYATA terakhir
    (bukan simulasi berdiri sendiri), baseline_* None kalau mesin belum
    pernah punya data sensor sungguhan sama sekali."""

    machine_name: str
    hypothetical_label: bool
    hypothetical_probability: float
    baseline_label: bool | None
    baseline_probability: float | None
    top_feature_name: str
    changed_features: dict[str, float]


WHAT_IF_PROMPT = """You are a predictive maintenance assistant for CNC machines.
Compare the following hypothetical (what-if) scenario against the real current condition of
machine {machine_name}. Reply in English, 2-4 sentences, stating the failure probability of both
conditions and whether the risk increases, decreases, or stays the same. Do NOT invent any data
not given below.

Write direct, definitive statements. Do not hedge with vague filler words such as "maybe",
"perhaps", "possibly", or "it seems".

Last real condition: {baseline_text}
Hypothetical scenario: {hypothetical_label_text} (failure probability {hypothetical_probability_pct}%)
Simulated changes: {changes_text}
Top contributing feature in the hypothetical scenario: {top_feature}
"""


def generate_what_if_narrative(context: WhatIfContext) -> str:
    if context.baseline_probability is not None:
        baseline_label_text = "failure predicted" if context.baseline_label else "normal"
        baseline_text = f"{baseline_label_text} (failure probability {round(context.baseline_probability * 100, 1)}%)"
    else:
        baseline_text = "(no real sensor data yet for this machine)"

    hypothetical_label_text = "failure predicted" if context.hypothetical_label else "normal"
    changes_text = (
        "; ".join(f"{k} set to {v}" for k, v in context.changed_features.items())
        or "(none — using the latest real data as-is)"
    )

    prompt = WHAT_IF_PROMPT.format(
        machine_name=context.machine_name,
        baseline_text=baseline_text,
        hypothetical_label_text=hypothetical_label_text,
        hypothetical_probability_pct=round(context.hypothetical_probability * 100, 1),
        changes_text=changes_text,
        top_feature=context.top_feature_name,
    )
    try:
        return chat([{"role": "user", "content": prompt}], model=settings.GROQ_MODEL, temperature=0.3)
    except Exception:
        logger.exception("generate_what_if_narrative: Groq call failed")
        if context.baseline_probability is not None:
            direction = (
                "increases" if context.hypothetical_probability > context.baseline_probability
                else "decreases" if context.hypothetical_probability < context.baseline_probability
                else "stays the same"
            )
            return (
                f"Hypothetical scenario: failure probability {direction} from "
                f"{round(context.baseline_probability * 100, 1)}% to "
                f"{round(context.hypothetical_probability * 100, 1)}%."
            )
        return (
            f"Hypothetical scenario: failure probability {round(context.hypothetical_probability * 100, 1)}% "
            "(no real data for this machine yet to compare against)."
        )
