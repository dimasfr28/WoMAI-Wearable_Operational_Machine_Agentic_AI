"""Grader — LLM (Groq) menilai relevansi dokumen terhadap query, Section 6.9."""
from __future__ import annotations

import json
import logging

from app.llm.groq_client import chat_json
from app.rag.retriever import RetrievedDocument

logger = logging.getLogger(__name__)

GRADE_PROMPT = """You are a document relevance grader for a retrieval-augmented generation system.
For each document below, determine whether it is relevant for answering the query.

Query: {query}

Documents:
{docs_block}

Reply ONLY in JSON format: {{"verdicts": [true/false, ...]}} with an array length exactly
matching the number of documents above, in the same order as the documents."""


def grade_documents(query: str, documents: list[RetrievedDocument]) -> tuple[str, list[bool]]:
    """Returns (grade, verdicts) where grade is 'relevant' if ratio of relevant docs >= 0.5."""
    if not documents:
        return "irrelevant", []

    docs_block = "\n\n".join(f"[{i}] {d.page_content[:800]}" for i, d in enumerate(documents))
    prompt = GRADE_PROMPT.format(query=query, docs_block=docs_block)

    try:
        raw = chat_json([{"role": "user", "content": prompt}])
        parsed = json.loads(raw)
        verdicts = [bool(v) for v in parsed.get("verdicts", [])]
        if len(verdicts) != len(documents):
            # pad/truncate defensively so downstream code never index-errors
            verdicts = (verdicts + [False] * len(documents))[: len(documents)]
    except Exception:
        logger.exception("grade_documents: LLM grading failed, defaulting to irrelevant (web fallback)")
        verdicts = [False] * len(documents)

    ratio = sum(verdicts) / len(verdicts) if verdicts else 0.0
    grade = "relevant" if ratio >= 0.5 else "irrelevant"
    return grade, verdicts
