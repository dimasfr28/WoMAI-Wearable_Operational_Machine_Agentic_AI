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
import os

# ragas phones home analytics on every scorer call unless told not to — this
# network blocks outbound DNS for hosts it doesn't need (see
# mineru-service/Dockerfile.dev's RES_OPTIONS comment for the same class of
# issue), so every call would otherwise eat a DNS-resolution failure and log
# noise for a request that was never going anywhere useful.
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

import instructor
from google import genai
from ragas.llms.adapters.instructor import InstructorLLM, InstructorModelArgs
from ragas.metrics.collections import Faithfulness

from app.config import settings

logger = logging.getLogger(__name__)


def evaluate_faithfulness(query: str, answer: str, contexts: list[str]) -> float | None:
    """Faithfulness score (0-1): how well `answer` is supported by `contexts`.

    Deliberately bypasses ragas.llms.llm_factory()'s own Google auto-wrapping:
    it wraps the client via instructor.from_genai(client), whose use_async
    defaults to False — producing a synchronous Instructor client that
    Faithfulness.ascore() then rejects, since ascore() is always async with
    no synchronous code path at the metric level. Constructing instructor's
    async client ourselves (use_async=True) and handing it directly to
    ragas's InstructorLLM wrapper sidesteps that."""
    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        async_client = instructor.from_genai(client, use_async=True)
        judge_llm = InstructorLLM(
            client=async_client,
            model=settings.GEMINI_MODEL,
            provider="google",
            model_args=InstructorModelArgs(),
        )
        scorer = Faithfulness(llm=judge_llm)
        result = asyncio.run(
            scorer.ascore(user_input=query, response=answer, retrieved_contexts=contexts)
        )
        return float(result.value)
    except Exception:
        logger.exception("evaluate_faithfulness: RAGAS judge failed")
        return None
