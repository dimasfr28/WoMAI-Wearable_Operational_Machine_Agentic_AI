"""Outbound Telegram notification on new sensor reading — see
docs/superpowers/specs/2026-08-16-telegram-notifications-design.md.

Synchronous, single HTTP call inside the caller's existing request handler.
No BackgroundTasks, no queue, no listener/poller of any kind — the AIC MVP
rules for this submission require request/response processing to stay
synchronous, and this is outbound-only (the bot never receives commands).
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.ml.predictor_clasification import ClasificationResult

logger = logging.getLogger(__name__)

_SEND_MESSAGE_URL = "https://api.telegram.org/bot{token}/sendMessage"


def notify_new_reading(
    machine_name: str,
    pred_result: ClasificationResult,
    horizon_probability: float | None = None,
    horizon_minutes: int | None = None,
    run_label: str | None = None,
    health_score: float | None = None,
    top_feature_name: str | None = None,
    cause_analysis_short: str | None = None,
) -> None:
    """Fire-and-forget: never raises, so a Telegram outage can never break
    sensor ingestion. No-op if either config value is unset.

    horizon_probability/horizon_minutes come from the separate "Probability
    Failure in +N Minute" model (_run_report_pipeline's horizon_result) —
    optional because that pipeline step can fail independently of the main
    classification (see routes_report.py's own try/except around it), so
    callers may not always have it available yet when they call this.

    run_label/health_score/top_feature_name/cause_analysis_short add detail
    beyond the bare label+probability so an operator can act on the alert
    without opening the dashboard — all optional/nullable because callers
    may not always have every piece (e.g. cause_analysis_short is only
    computed when pred_result.label is True)."""
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return

    probability_pct = pred_result.probability * 100
    if pred_result.label:
        text = f"⚠️ {machine_name} — FAILURE predicted ({probability_pct:.1f}%)"
    else:
        text = f"✅ {machine_name} — Normal ({probability_pct:.1f}%)"
    if run_label:
        text += f"\nRun: {run_label}"
    if health_score is not None:
        text += f"\nHealth Score: {health_score:.1f}/100"
    if top_feature_name:
        text += f"\nTop contributing factor: {top_feature_name}"
    if cause_analysis_short:
        text += f"\nRoot cause: {cause_analysis_short}"
    if horizon_probability is not None:
        text += f"\nFailure in +{horizon_minutes or 10} Minute: {horizon_probability * 100:.1f}%"

    url = _SEND_MESSAGE_URL.format(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        response = httpx.post(
            url,
            json={"chat_id": settings.TELEGRAM_CHAT_ID, "text": text},
            timeout=5.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # Never log `exc`/`response`/`url` here: httpx.HTTPStatusError's
        # message and repr embed the request URL, which contains the raw
        # Telegram bot token (Telegram puts the token in the URL path).
        # Logging the exception object (e.g. via logger.exception) would
        # leak the live bot token into the logs in cleartext.
        logger.error(
            "notify_new_reading: Telegram API returned HTTP %s",
            exc.response.status_code,
        )
    except Exception:
        logger.exception("notify_new_reading: failed to send Telegram notification")
