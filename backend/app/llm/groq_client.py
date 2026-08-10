"""Groq client — dipakai crag_graph.py & generate_final_report()."""
from __future__ import annotations

from functools import lru_cache

from groq import Groq

from app.config import settings


@lru_cache(maxsize=1)
def _get_client() -> Groq:
    return Groq(api_key=settings.GROQ_API_KEY)


def chat(messages: list[dict], model: str | None = None, temperature: float = 0.2) -> str:
    """Simple sync chat completion wrapper. messages: [{"role": "user"/"system", "content": ...}]"""
    client = _get_client()
    response = client.chat.completions.create(
        model=model or settings.GROQ_MODEL,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


def chat_json(messages: list[dict], model: str | None = None) -> str:
    """Chat completion requesting JSON-mode output (used by grader.py)."""
    client = _get_client()
    response = client.chat.completions.create(
        model=model or settings.GROQ_MODEL,
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content or "{}"
