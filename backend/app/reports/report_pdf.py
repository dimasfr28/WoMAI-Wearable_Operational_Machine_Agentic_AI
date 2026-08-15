"""Render Machine Report PDF (rancangan.txt Section 7, revised per "Machine
Report REVISI") — assembles a Jinja2 HTML template from ReportOut (already
computed by _run_report_pipeline, see routes_report.py) + historical
condition log, then renders it to PDF via WeasyPrint. All NUMBERS come from
ReportOut/DB (deterministic); only the narrative prose (condition_summary/
ai_diagnosis/summary) is LLM-generated, via report_narrative.py — same
"LLM writes prose, Python computes numbers" split as
generate_early_warning_narrative().

Financial impact ("Estimated Financial Impact" in the rancangan.txt draft) is
intentionally NOT implemented — there is no cost-per-hour/production-rate
data source anywhere in this system yet, and fabricating placeholder numbers
in a formal report would be worse than omitting the section.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from app.ml.predictor_clasification import PARAM_META

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


@dataclass
class ConditionLogRow:
    timestamp: str
    air_temperature_k: float
    process_temperature_k: float
    rotational_speed_rpm: int
    tool_wear_min: float
    health_score: float
    failure_risk_pct: float


def _risk_level(probability: float) -> str:
    if probability >= 0.7:
        return "Critical"
    if probability >= 0.4:
        return "High"
    if probability >= 0.15:
        return "Medium"
    return "Low"


def _operating_status(predicted_label: bool, probability: float) -> str:
    if predicted_label:
        return "Failure"
    if probability >= 0.15:
        return "Warning"
    return "Normal"


def _shap_interpretation(feature_name: str, value: float, shap_value: float) -> str:
    _, label, unit = PARAM_META.get(feature_name, (feature_name, feature_name, ""))
    direction = "increases" if shap_value > 0 else "decreases"
    return f"{label} is currently {value}{unit} — this {direction} failure risk."


def _failure_contribution_scores(features: list) -> list[int]:
    """Normalizes raw SHAP values into a 0-100 "Failure Contribution" score
    (Machine Report REVISI point 3) — each feature's share of the TOTAL
    |SHAP| across the features shown in this report, scaled to 100, so the
    scores are directly comparable at a glance without needing to know SHAP's
    underlying units (log-odds). Same relative-share approach as the
    shap_contribution_pct already used by routes_machine.py's early warning
    cards, applied here to the report's SHAP table."""
    total_abs = sum(abs(f.shap_value) for f in features)
    if total_abs <= 0:
        return [0 for _ in features]
    return [round(abs(f.shap_value) / total_abs * 100) for f in features]


def _parse_rag_answer_sections(answer_text: str) -> dict[str, str]:
    """Splits RAG_ANSWER_PROMPT's markdown-headed answer ("## What Is the
    Problem" / "## Handling Procedure" / "## Affected Part / Component")
    into per-section HTML, dropping the trailing "PART_NAMES: ..." line
    (Machine Report REVISI point 5 — the report renders real HTML
    subsections instead of dumping the raw markdown as preformatted text,
    and the PART_NAMES line is for programmatic extraction only, not for
    display)."""
    # Strip the machine-readable PART_NAMES line before splitting into
    # sections — it's not part of any of the three named sections' content.
    body = re.sub(r"(?im)^\s*PART_NAMES:.*$", "", answer_text).strip()

    sections: dict[str, str] = {}
    chunks = re.split(r"(?m)^##\s+(.+?)\s*$", body)
    # re.split with a capturing group yields: [pre-text, heading1, body1, heading2, body2, ...]
    for i in range(1, len(chunks), 2):
        heading = chunks[i].strip().lower()
        content = chunks[i + 1].strip() if i + 1 < len(chunks) else ""
        html = content.replace("\n", "<br>")
        if "what is the problem" in heading:
            sections["what_is_the_problem"] = html
        elif "handling procedure" in heading:
            sections["handling_procedure"] = html
        elif "affected part" in heading or "component" in heading:
            sections["affected_part"] = html
    return sections


def render_machine_report_pdf(
    *,
    machine_id: str,
    machine_name: str,
    report_number: str,
    report_out,  # ReportOut (app.schemas.report) — kept untyped to avoid a
    # circular import (routes_report.py imports this module's render function).
    narrative: dict,
    condition_log: list[ConditionLogRow],
    output_path: Path,
) -> None:
    template = _env.get_template("machine_report.html.j2")

    predicted_label = report_out.prediction.predicted_label
    probability = report_out.prediction.failure_probability
    operating_status = _operating_status(predicted_label, probability)
    failure_risk_pct = round(probability * 100, 1)
    risk_level = _risk_level(probability)

    horizon_pct = (
        round(report_out.horizon_prediction.failure_probability * 100, 1)
        if report_out.horizon_prediction is not None
        else None
    )
    horizon_minutes = report_out.horizon_prediction.horizon_minutes if report_out.horizon_prediction is not None else None

    contribution_scores = _failure_contribution_scores(report_out.shap.features)
    shap_features = [
        {
            "label": PARAM_META.get(f.feature_name, (f.feature_name, f.feature_name, ""))[1],
            "contribution_score": score,
            "interpretation": _shap_interpretation(f.feature_name, f.value, f.shap_value),
        }
        for f, score in zip(report_out.shap.features, contribution_scores)
    ]
    top_feature_label = shap_features[0]["label"] if shap_features else "-"

    root_cause = None
    if report_out.root_cause is not None:
        sections = _parse_rag_answer_sections(report_out.root_cause.answer)
        root_cause = {
            "what_is_the_problem": sections.get("what_is_the_problem"),
            "handling_procedure": sections.get("handling_procedure"),
            "affected_part": sections.get("affected_part"),
            "used_web_fallback": report_out.root_cause.used_web_fallback,
        }

    # report_out.part_prices holds (at most) one representative MARKETPLACE
    # LISTING per part named in PART_NAMES (routes_report.py's
    # _run_report_pipeline calls search_part_price once per part and keeps
    # only its top match) — Machine Report REVISI point 6: Estimated Machine
    # Part Cost must have one row per Machine Parts Checking row, plus a
    # total. Dedup by part_name defensively (in case of a re-run/retry
    # producing duplicate DB rows for the same part), preserving first-seen
    # order (PART_NAMES's "most important first").
    part_prices: list[dict] = []
    seen_parts: set[str] = set()
    total_min = 0.0
    total_max = 0.0
    total_has_any_price = False
    total_currency = None
    for p in report_out.part_prices:
        if p.part_name in seen_parts:
            continue
        seen_parts.add(p.part_name)
        has_price = p.price_min is not None and p.price_max is not None
        if has_price:
            total_min += p.price_min
            total_max += p.price_max
            total_has_any_price = True
            total_currency = p.currency
        part_prices.append(
            {
                "part_name": p.part_name,
                "price_text": (
                    f"{p.currency} {p.price_min:,.0f} - {p.price_max:,.0f}" if has_price else "Price not available"
                ),
                "source_url": p.source_url,
            }
        )
    total_cost_text = (
        f"{total_currency} {total_min:,.0f} - {total_max:,.0f}" if total_has_any_price else None
    )

    # Machine Parts Checking (merged into "Failure Risk Prediction", point 4)
    # shows EVERY part CRAG named (Machine Report REVISI point 6).
    parts_checking = []
    part_names_for_checking = (
        report_out.root_cause.part_names
        if report_out.root_cause and report_out.root_cause.part_names
        else ([report_out.root_cause.part_name] if report_out.root_cause and report_out.root_cause.part_name else [])
    )
    for name in part_names_for_checking:
        parts_checking.append(
            {
                "name": name,
                "condition": "At-Risk Condition" if predicted_label else "Good Condition",
                "finding": report_out.cause_analysis_short or "Identified from automatic root-cause analysis.",
            }
        )

    html_str = template.render(
        machine_id=machine_id,
        machine_name=machine_name,
        report_number=report_number,
        report_datetime=datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC"),
        operating_status=operating_status,
        sensor=report_out.sensor,
        prediction=report_out.prediction,
        horizon_pct=horizon_pct,
        horizon_minutes=horizon_minutes,
        failure_risk_pct=failure_risk_pct,
        risk_level=risk_level,
        top_feature_label=top_feature_label,
        shap_features=shap_features,
        narrative=narrative,
        parts_checking=parts_checking,
        root_cause=root_cause,
        part_prices=part_prices,
        total_cost_text=total_cost_text,
        condition_log=condition_log,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_str).write_pdf(str(output_path))
