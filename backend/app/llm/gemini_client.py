"""Gemini client — active LLM provider, replacing groq_client.py (kept in the
tree as a fallback reference, no longer imported by any call site).

Reason for the switch: this app's Groq key is capped at 8000 TPM (tokens per
minute, shared across every model on the key) and, after enough testing in
one day, also hit openai/gpt-oss-120b's separate 200k TPD (tokens per day)
cap — both confirmed via response headers/error bodies. Gemini's free tier
(gemini-3.1-flash-lite here) is at minimum 250k TPM, ~30x Groq's ceiling, which
comfortably covers this app's multi-call-per-request pipeline (CRAG alone
makes 5-10+ LLM calls per failure submission).

Same chat()/chat_json() surface as groq_client.py on purpose, so every call
site (crag_graph.py, grader.py, final_report.py, report_narrative.py,
bot/graph.py, routes_chat.py) only needed an import swap, not a rewrite.
"""
from __future__ import annotations

from functools import lru_cache

from google import genai
from google.genai import types

from app.config import settings

_MAX_OUTPUT_TOKENS = 2500


@lru_cache(maxsize=1)
def _get_client() -> genai.Client:
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _to_gemini_contents(messages: list[dict]) -> tuple[str | None, list[types.Content]]:
    """OpenAI-style messages -> (system_instruction, contents). Every call
    site builds messages with role in {"system", "user", "assistant"} —
    Gemini takes system prompts out-of-band via system_instruction, and
    calls the assistant role "model" instead of "assistant"."""
    system_instruction: str | None = None
    contents: list[types.Content] = []
    for msg in messages:
        role = msg.get("role")
        text = msg.get("content", "")
        if role == "system":
            system_instruction = text if system_instruction is None else f"{system_instruction}\n\n{text}"
        else:
            gemini_role = "model" if role == "assistant" else "user"
            contents.append(types.Content(role=gemini_role, parts=[types.Part(text=text)]))
    return system_instruction, contents


def chat(messages: list[dict], model: str | None = None, temperature: float = 0.2) -> str:
    """Simple sync chat completion wrapper. messages: [{"role": "user"/"system", "content": ...}]"""
    client = _get_client()
    system_instruction, contents = _to_gemini_contents(messages)
    response = client.models.generate_content(
        model=model or settings.GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
        ),
    )
    return response.text or ""


def chat_json(messages: list[dict], model: str | None = None) -> str:
    """Chat completion requesting JSON-mode output (used by grader.py etc)."""
    client = _get_client()
    system_instruction, contents = _to_gemini_contents(messages)
    response = client.models.generate_content(
        model=model or settings.GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
        ),
    )
    return response.text or "{}"
