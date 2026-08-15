from __future__ import annotations

from typing import Literal, TypedDict


class BotGraphState(TypedDict, total=False):
    user_message: str
    history: list[dict]
    session_machine_id: str | None
    resolved_machine_id: str | None
    intent: Literal["machine_query", "chitchat"]
    needs_input_message: str | None
    tool_calls_count: int
    tool_results: list[dict]
    final_response: str
    next_action: str | None
