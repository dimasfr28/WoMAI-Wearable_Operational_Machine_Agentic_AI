"""Groq client — dipakai crag_graph.py & generate_final_report()."""
from __future__ import annotations

from functools import lru_cache

from groq import Groq

from app.config import settings


@lru_cache(maxsize=1)
def _get_client() -> Groq:
    return Groq(api_key=settings.GROQ_API_KEY)


# This account's Groq key is capped at 8000 TPM (tokens per minute) —
# confirmed via response headers, applies account-wide across every model on
# this key, not just GROQ_MODEL. Reasoning models (tried qwen/qwen3.6-27b,
# openai/gpt-oss-20b) spend most of their completion budget on an internal
# <think> pass before answering — with a small max_tokens the response gets
# cut off with ZERO actual answer content (in JSON mode that's a hard 400
# "Failed to validate JSON", not just truncation), and raising max_tokens
# enough to fix that alone exceeds the 8000 TPM ceiling once you add prompt
# tokens. openai/gpt-oss-120b reliably finishes real prompts from this app
# (RAG_QUERY_PROMPT etc.) in ~1500-2500 completion tokens with finish_reason
# "stop" (not truncated) — picked for being token-efficient enough to leave
# headroom for this app's multi-call-per-request pipeline (CRAG alone makes
# 5-10+ LLM calls per failure submission) within the same 8000 TPM budget.
_MAX_COMPLETION_TOKENS = 2500

# openai/gpt-oss-* models use OpenAI's "Harmony" multi-channel response
# format internally (<|channel|>analysis<|message|>...<|channel|>final<|message|>...)
# instead of a plain <think> tag. Groq's reasoning_format="hidden" is meant to
# strip all of that server-side, but observed in practice (real prompts from
# this app's CRAG pipeline) it sometimes leaks: content comes back as an
# earlier channel's text, the literal "<|channel|>final<|message|>" marker,
# then the true final answer — i.e. the real answer duplicated with garbage
# stuck in front of it. Defensive fix regardless of Groq/model-side behavior:
# if that marker is present, keep only the text after its LAST occurrence
# (the true final channel); text without the marker passes through untouched.
_HARMONY_FINAL_MARKER = "<|channel|>final<|message|>"


def _strip_harmony_leak(text: str) -> str:
    if _HARMONY_FINAL_MARKER not in text:
        return text
    return text.rsplit(_HARMONY_FINAL_MARKER, 1)[1].strip()


def chat(messages: list[dict], model: str | None = None, temperature: float = 0.2) -> str:
    """Simple sync chat completion wrapper. messages: [{"role": "user"/"system", "content": ...}]"""
    client = _get_client()
    response = client.chat.completions.create(
        model=model or settings.GROQ_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=_MAX_COMPLETION_TOKENS,
        # "hidden" strips the <think> block so callers always get the final
        # answer only — ignored (harmlessly) by non-reasoning models.
        extra_body={"reasoning_format": "hidden"},
    )
    return _strip_harmony_leak(response.choices[0].message.content or "")


def chat_json(messages: list[dict], model: str | None = None) -> str:
    """Chat completion requesting JSON-mode output (used by grader.py)."""
    client = _get_client()
    response = client.chat.completions.create(
        model=model or settings.GROQ_MODEL,
        messages=messages,
        temperature=0,
        max_tokens=_MAX_COMPLETION_TOKENS,
        response_format={"type": "json_object"},
        extra_body={"reasoning_format": "hidden"},
    )
    return _strip_harmony_leak(response.choices[0].message.content or "{}")
