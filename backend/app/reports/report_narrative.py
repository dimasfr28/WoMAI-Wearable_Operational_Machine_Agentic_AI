"""LLM narrative untuk Machine Report (rancangan.txt Section 7, revisi
"Machine Report REVISI" point 7) — 3 bagian prosa dalam SATU panggilan LLM
(skema JSON, mengikuti pola app/rag/final_report.py's EARLY_WARNING_PROMPT):
AI Condition Summary (section 1), AI Diagnosis (section "Failure Risk
Prediction"), Summary (closing section — exactly 2 paragraphs of exactly 4
sentences each, replacing the old single-sentence "Final Recommendation").

Semua ANGKA di laporan (parameter, health score, failure risk, dst) dirakit
deterministik di report_pdf.py dari ReportOut yang sudah ada — LLM di sini
HANYA menulis kalimat penjelas, sama seperti generate_early_warning_narrative().
"""
from __future__ import annotations

import json
import logging

from app.config import settings
from app.llm.gemini_client import chat_json

logger = logging.getLogger(__name__)

MACHINE_REPORT_NARRATIVE_PROMPT = """You are a predictive maintenance assistant for CNC machines.
Reply ONLY in JSON with exactly this schema (no other text):
{{
  "condition_summary": "<2-4 sentences in English on the machine's condition, based on the ML results and sensor data>",
  "ai_diagnosis": "<2-3 sentences in English explaining WHY the current condition is associated with failure risk (or why it is normal)>",
  "summary": "<EXACTLY 2 paragraphs in English, separated by a single \\n\\n, each paragraph containing EXACTLY 4 sentences. Paragraph 1 recaps the machine's condition, the failure risk, and the root cause/top contributing factor. Paragraph 2 states the recommended action, its priority/urgency, and a follow-up step. Count your sentences before answering.>"
}}

CITATION RULE: if "Root cause" below contains a citation in "(Source Name)" format, preserve it
exactly when you restate that claim in ai_diagnosis or summary — do not drop or paraphrase away a
citation.

DIRECTNESS RULE: write direct, definitive statements grounded in the data below. Do not hedge
with vague filler words such as "maybe", "perhaps", "possibly", "it seems", or "it might be".

Data:
- Machine name: {machine_name}
- Operating status: {operating_status}
- Health Score: {health_score}/100
- Failure Risk: {failure_risk_pct}%
- Risk Level: {risk_level}
- Top contributing feature (SHAP): {top_feature}
- Root cause (if any): {root_cause_summary}
- Technical recommendation (if any): {recommended_action_summary}
"""


def generate_machine_report_narrative(
    *,
    machine_name: str,
    operating_status: str,
    health_score: float,
    failure_risk_pct: float,
    risk_level: str,
    top_feature: str,
    root_cause_summary: str | None,
    recommended_action_summary: str | None,
) -> dict:
    prompt = MACHINE_REPORT_NARRATIVE_PROMPT.format(
        machine_name=machine_name,
        operating_status=operating_status,
        health_score=health_score,
        failure_risk_pct=failure_risk_pct,
        risk_level=risk_level,
        top_feature=top_feature,
        root_cause_summary=root_cause_summary or "(none — normal condition)",
        recommended_action_summary=recommended_action_summary or "(no adjustment recommended)",
    )
    try:
        raw = chat_json([{"role": "user", "content": prompt}], model=settings.GEMINI_MODEL)
        data = json.loads(raw)
        return {
            "condition_summary": data.get("condition_summary") or "",
            "ai_diagnosis": data.get("ai_diagnosis") or "",
            "summary": data.get("summary") or "",
        }
    except Exception:
        logger.exception("generate_machine_report_narrative: Groq call failed")
        fallback_p1 = (
            f"Machine {machine_name} is currently in {operating_status} status with a health score of "
            f"{health_score}/100. The failure risk is {failure_risk_pct}%, classified as {risk_level} risk. "
            f"{top_feature} is the top contributing factor to this result. "
            f"{recommended_action_summary or 'No specific root cause was identified for this reading.'}"
        )
        fallback_p2 = (
            "Continue routine monitoring per the preventive maintenance schedule. "
            "Review the technical recommendation and diagnosis above before the next scheduled run. "
            "Escalate to a technician if the condition persists or worsens. "
            "Re-check this machine's status after the next sensor reading is submitted."
        )
        return {
            "condition_summary": (
                f"Machine {machine_name} is currently in {operating_status} status with a health score of {health_score}/100."
            ),
            "ai_diagnosis": f"{top_feature} is the top contributing factor to the current failure risk.",
            "summary": f"{fallback_p1}\n\n{fallback_p2}",
        }
