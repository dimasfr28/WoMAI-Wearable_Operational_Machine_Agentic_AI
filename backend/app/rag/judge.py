"""LLM-as-a-judge for CRAG root-cause answers (RAGAS Faithfulness).

Scores whether generate_answer()'s output (crag_graph.py) is grounded in its
retrieved_contexts. Called ONCE, synchronously, inside routes_report.py's
_run_report_pipeline right after run_crag() returns — i.e. only when CRAG
itself runs (predicted_label=True) — and only for logging (proposal/demo
evidence of RAG quality). No DB column, no effect on the chat response, no
background job: fits the AIC MVP "synchronous request/response only"
constraint as one extra LLM call in the same request.

A judge failure must never break the report pipeline it's observing, so every
error here is caught and surfaced as None rather than raised.
"""
from __future__ import annotations

import asyncio
import logging

from google import genai
from ragas.llms import llm_factory
from ragas.metrics.collections import Faithfulness

from app.config import settings

logger = logging.getLogger(__name__)


def evaluate_faithfulness(query: str, answer: str, contexts: list[str]) -> float | None:
    """Faithfulness score (0-1): how well `answer` is supported by `contexts`."""
    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        judge_llm = llm_factory(settings.GEMINI_MODEL, provider="google", client=client)
        scorer = Faithfulness(llm=judge_llm)
        result = asyncio.run(
            scorer.ascore(user_input=query, response=answer, retrieved_contexts=contexts)
        )
        return float(result.value)
    except Exception:
        logger.exception("evaluate_faithfulness: RAGAS judge failed")
        return None
