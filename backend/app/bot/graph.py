from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Generator

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.bot.prompts import (
    build_chitchat_messages,
    build_resolve_machine_messages,
    build_router_messages,
    build_synthesize_messages,
    build_tool_decider_messages,
)
from app.bot.state import BotGraphState
from app.bot.tools import (
    execute_bot_tool,
    get_machine_info_tool,
    list_machines_tool,
)
from app.db.models import Machine
from app.llm.groq_client import chat, chat_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node Implementations
# ---------------------------------------------------------------------------


def router_node(state: BotGraphState) -> BotGraphState:
    """Classify user query into machine_query vs chitchat."""
    user_message = state.get("user_message", "")
    history = state.get("history", [])

    messages = build_router_messages(user_message=user_message, history=history)
    try:
        raw = chat_json(messages)
        parsed = json.loads(raw)
        intent = parsed.get("intent", "machine_query")
        if intent not in ("machine_query", "chitchat"):
            intent = "machine_query"
    except Exception:
        logger.exception("router_node: chat_json failed, defaulting to machine_query")
        intent = "machine_query"

    return {**state, "intent": intent}


def chitchat_node(state: BotGraphState) -> BotGraphState:
    """Generate friendly general conversation response."""
    user_message = state.get("user_message", "")
    history = state.get("history", [])

    messages = build_chitchat_messages(user_message=user_message, history=history)
    try:
        reply = chat(messages)
    except Exception:
        logger.exception("chitchat_node: chat failed")
        reply = "Halo! Saya adalah Predixia Bot, asisten pemantauan dan predictive maintenance mesin CNC. Ada yang bisa saya bantu terkait mesin atau data sensor Anda?"

    return {**state, "final_response": reply}


def resolve_machine_node(state: BotGraphState, db: Session | None = None) -> BotGraphState:
    """Match user's machine mention against DB registered machines or detect ambiguity."""
    if state.get("intent") == "chitchat":
        return state

    user_message = state.get("user_message", "")
    history = state.get("history", [])
    session_machine_id = state.get("session_machine_id")

    machines: list[dict[str, Any]] = []
    if db is not None:
        try:
            machines = list_machines_tool(db=db)
        except Exception:
            logger.exception("resolve_machine_node: list_machines_tool failed")
            machines = []

    # If no machines in DB, proceed without machine context
    if not machines:
        return {**state, "resolved_machine_id": None, "needs_input_message": None}

    # If only 1 machine exists and no machine mentioned, default to it
    if len(machines) == 1 and not session_machine_id:
        single_machine_id = str(machines[0].get("id"))
        return {**state, "resolved_machine_id": single_machine_id, "needs_input_message": None}

    messages = build_resolve_machine_messages(
        user_message=user_message,
        machines=machines,
        session_machine=session_machine_id,
        history=history,
    )

    try:
        raw = chat_json(messages)
        parsed = json.loads(raw)
        is_ambiguous = bool(parsed.get("is_ambiguous") or parsed.get("needs_input"))
        clarification_msg = parsed.get("clarification_message") or parsed.get("clarification")

        if is_ambiguous and clarification_msg:
            return {
                **state,
                "resolved_machine_id": None,
                "needs_input_message": str(clarification_msg),
                "final_response": str(clarification_msg),
            }

        resolved_id = parsed.get("resolved_machine_id") or parsed.get("machine_id")
        if isinstance(resolved_id, str) and resolved_id.strip().lower() in ("null", "none", ""):
            resolved_id = None
        valid_id = str(resolved_id).strip() if resolved_id else session_machine_id
        if isinstance(valid_id, str) and valid_id.strip().lower() in ("null", "none", ""):
            valid_id = None
        return {
            **state,
            "resolved_machine_id": valid_id,
            "needs_input_message": None,
        }

    except Exception:
        logger.exception("resolve_machine_node: failed to resolve machine, falling back to session machine")
        return {
            **state,
            "resolved_machine_id": session_machine_id,
            "needs_input_message": None,
        }


def tool_decider_node(state: BotGraphState) -> BotGraphState:
    """Decide which tool to call next or finish."""
    if state.get("needs_input_message"):
        return {**state, "next_action": "synthesize"}

    tool_calls_count = state.get("tool_calls_count", 0)
    if tool_calls_count >= 5:
        return {**state, "next_action": "synthesize"}

    user_message = state.get("user_message", "")
    history = state.get("history", [])
    resolved_machine_id = state.get("resolved_machine_id")
    tool_results = state.get("tool_results", [])

    messages = build_tool_decider_messages(
        user_message=user_message,
        resolved_machine=resolved_machine_id,
        tool_results=tool_results,
        tool_calls_count=tool_calls_count,
        history=history,
    )

    try:
        raw = chat_json(messages)
        decision = json.loads(raw)
        action = decision.get("action", "finish")
        if action == "call_tool" and decision.get("tool_name"):
            tool_args = decision.get("tool_args") or {}
            # Inject resolved_machine_id if not present
            if resolved_machine_id and not tool_args.get("machine_id") and decision.get("tool_name") in ("search_sensor_data", "get_machine_info"):
                tool_args["machine_id"] = resolved_machine_id

            return {
                **state,
                "next_action": "call_tool",
                "_pending_tool": {
                    "tool_name": decision.get("tool_name"),
                    "tool_args": tool_args,
                    "status_message": decision.get("status_message") or f"Menjalankan {decision.get('tool_name')}...",
                },
            }
        else:
            return {**state, "next_action": "synthesize"}
    except Exception:
        logger.exception("tool_decider_node: failed, falling back to synthesize")
        return {**state, "next_action": "synthesize"}


def tool_executor_node(state: BotGraphState, db: Session | None = None) -> BotGraphState:
    """Execute decided tool and record output in tool_results."""
    pending = state.get("_pending_tool")
    if not pending or not db:
        return {**state, "next_action": "synthesize"}

    tool_name = pending.get("tool_name", "")
    tool_args = pending.get("tool_args", {})

    output = execute_bot_tool(tool_name=tool_name, args=tool_args, db=db)

    results = list(state.get("tool_results", []))
    results.append({
        "tool_name": tool_name,
        "tool_args": tool_args,
        "output": output,
    })

    return {
        **state,
        "tool_results": results,
        "tool_calls_count": state.get("tool_calls_count", 0) + 1,
        "_pending_tool": None,
    }


def synthesize_node(state: BotGraphState, db: Session | None = None) -> BotGraphState:
    """Synthesize final response from gathered data and tool results."""
    # If already set (e.g. from chitchat or needs_input), return as is
    if state.get("final_response"):
        return state

    user_message = state.get("user_message", "")
    history = state.get("history", [])
    resolved_machine_id = state.get("resolved_machine_id")
    tool_results = state.get("tool_results", [])

    machine_context = ""
    if resolved_machine_id and db is not None:
        try:
            info = get_machine_info_tool(db=db, machine_id=resolved_machine_id)
            if info:
                machine_context = json.dumps(info, ensure_ascii=False)
        except Exception:
            machine_context = f"Machine ID: {resolved_machine_id}"
    elif resolved_machine_id:
        machine_context = f"Machine ID: {resolved_machine_id}"

    tool_results_lines = []
    for res in tool_results:
        t_name = res.get("tool_name")
        t_args = json.dumps(res.get("tool_args", {}), ensure_ascii=False)
        t_out = res.get("output", "")
        tool_results_lines.append(f"Tool: {t_name}({t_args})\nHasil:\n{t_out}\n---")
    tool_results_context = "\n".join(tool_results_lines)

    messages = build_synthesize_messages(
        user_message=user_message,
        machine_context=machine_context,
        tool_results_context=tool_results_context,
        history=history,
    )

    try:
        reply = chat(messages)
    except Exception:
        logger.exception("synthesize_node: chat failed")
        reply = "Maaf, terjadi kendala teknis saat menyusun analisis. Silakan coba kembali sesaat lagi."

    return {**state, "final_response": reply}


# ---------------------------------------------------------------------------
# StateGraph Builder
# ---------------------------------------------------------------------------


def build_bot_graph(db: Session | None = None):
    """Build and compile the LangGraph StateGraph for the bot agent."""
    workflow = StateGraph(BotGraphState)

    workflow.add_node("router", router_node)
    workflow.add_node("chitchat", chitchat_node)
    workflow.add_node("resolve_machine", lambda s: resolve_machine_node(s, db=db))
    workflow.add_node("tool_decider", tool_decider_node)
    workflow.add_node("tool_executor", lambda s: tool_executor_node(s, db=db))
    workflow.add_node("synthesize", lambda s: synthesize_node(s, db=db))

    workflow.set_entry_point("router")

    workflow.add_conditional_edges(
        "router",
        lambda s: s.get("intent", "machine_query"),
        {
            "chitchat": "chitchat",
            "machine_query": "resolve_machine",
        },
    )

    workflow.add_edge("chitchat", END)

    workflow.add_conditional_edges(
        "resolve_machine",
        lambda s: "needs_input" if s.get("needs_input_message") else "tools",
        {
            "needs_input": END,
            "tools": "tool_decider",
        },
    )

    workflow.add_conditional_edges(
        "tool_decider",
        lambda s: "execute" if s.get("next_action") == "call_tool" and s.get("tool_calls_count", 0) < 5 else "synthesize",
        {
            "execute": "tool_executor",
            "synthesize": "synthesize",
        },
    )

    workflow.add_edge("tool_executor", "tool_decider")
    workflow.add_edge("synthesize", END)

    return workflow.compile()


# ---------------------------------------------------------------------------
# SSE Streaming Agent Runner
# ---------------------------------------------------------------------------


def run_bot_agent(
    db: Session,
    user_message: str,
    history: list[dict] | None = None,
    session_obj: Any = None,
    session_machine_id: str | None = None,
    stream_callback: Any = None,
) -> Generator[dict[str, Any], None, None]:
    """Execute bot agent and yield structured events matching the SSE contract:

    - {"type": "status", "message": "..."}
    - {"type": "tool_call", "name": "...", "machine_id": "...", "query": "..."}
    - {"type": "needs_input", "message": "..."}
    - {"type": "text", "delta": "..."}
    - {"type": "error", "message": "..."}
    """
    def _emit(event: dict[str, Any]) -> dict[str, Any]:
        if callable(stream_callback):
            try:
                stream_callback(event)
            except Exception:
                pass
        return event

    try:
        # Determine initial session machine
        init_machine_id = session_machine_id
        if not init_machine_id and session_obj is not None and getattr(session_obj, "machine_id", None):
            init_machine_id = str(session_obj.machine_id)

        state: BotGraphState = {
            "user_message": user_message,
            "history": history or [],
            "session_machine_id": init_machine_id,
            "resolved_machine_id": init_machine_id,
            "intent": "machine_query",
            "needs_input_message": None,
            "tool_calls_count": 0,
            "tool_results": [],
            "final_response": "",
        }

        # 1. Router step
        yield _emit({"type": "status", "message": "Menganalisis pesan..."})
        state = router_node(state)

        # 2A. Chitchat flow
        if state.get("intent") == "chitchat":
            yield _emit({"type": "status", "message": "Mengetik balasan..."})
            state = chitchat_node(state)
            reply = state.get("final_response", "")
            words = reply.split(" ")
            for i, word in enumerate(words):
                sep = " " if i < len(words) - 1 else ""
                yield _emit({"type": "text", "delta": word + sep})
            return

        # 2B. Resolve Machine step
        yield _emit({"type": "status", "message": "Mengidentifikasi mesin..."})
        state = resolve_machine_node(state, db=db)

        # Handle ambiguity
        if state.get("needs_input_message"):
            needs_input_msg = state["needs_input_message"]
            yield _emit({"type": "needs_input", "message": needs_input_msg})
            return

        # Persist resolved machine to session if changed
        resolved_id = state.get("resolved_machine_id")
        if resolved_id and session_obj is not None and hasattr(session_obj, "machine_id"):
            try:
                m_uuid = uuid.UUID(str(resolved_id))
                if session_obj.machine_id != m_uuid:
                    session_obj.machine_id = m_uuid
                    db.add(session_obj)
                    db.commit()
            except Exception:
                logger.exception("run_bot_agent: failed to update session machine_id")

        # 3. Tool ReAct Loop (max 5 iterations)
        while state.get("tool_calls_count", 0) < 5:
            state = tool_decider_node(state)
            if state.get("next_action") != "call_tool":
                break

            pending = state.get("_pending_tool") or {}
            tool_name = pending.get("tool_name", "")
            tool_args = pending.get("tool_args", {})
            status_msg = pending.get("status_message") or f"Menjalankan {tool_name}..."

            yield _emit({"type": "status", "message": status_msg})
            yield _emit({
                "type": "tool_call",
                "name": tool_name,
                "machine_id": tool_args.get("machine_id") or state.get("resolved_machine_id"),
                "query": tool_args.get("query") or tool_args.get("query_text"),
            })

            state = tool_executor_node(state, db=db)

        # 4. Synthesize & Stream
        yield _emit({"type": "status", "message": "Menyusun jawaban..."})
        state = synthesize_node(state, db=db)
        final_text = state.get("final_response", "")

        words = final_text.split(" ")
        for i, word in enumerate(words):
            sep = " " if i < len(words) - 1 else ""
            yield _emit({"type": "text", "delta": word + sep})

    except Exception as exc:
        logger.exception("run_bot_agent encountered an error")
        yield _emit({"type": "error", "message": f"Terjadi kesalahan: {str(exc)}"})
