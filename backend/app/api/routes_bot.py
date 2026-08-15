from __future__ import annotations

import json
import logging
import uuid as uuid_module
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.bot.graph import run_bot_agent
from app.db.models import BotMessage, BotSession, User
from app.db.session import SessionLocal, get_db
from app.schemas.bot import BotIn, BotMessageOut, BotSessionDetailOut, BotSessionOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bot", tags=["bot"])


def _sse(event: dict) -> str:
    """Format dictionary event into Server-Sent Events (SSE) data frame."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _resolve_session_uuid(user: User, session_id: str) -> uuid_module.UUID:
    """Derive deterministic session UUID from user.id and session_id string."""
    return uuid_module.uuid5(uuid_module.NAMESPACE_URL, f"{user.id}:{session_id}")


def _get_or_create_session(
    db: Session, user: User, session_id_str: str, message: str = ""
) -> BotSession:
    """Retrieve existing bot session by UUID or user-namespaced ID, or create a new one."""
    session = None
    try:
        raw_uuid = uuid_module.UUID(session_id_str)
        session = (
            db.query(BotSession)
            .filter(BotSession.id == raw_uuid, BotSession.user_id == user.id)
            .first()
        )
    except (ValueError, AttributeError):
        pass

    if session is None:
        session_uuid = _resolve_session_uuid(user, session_id_str)
        session = (
            db.query(BotSession)
            .filter(BotSession.id == session_uuid, BotSession.user_id == user.id)
            .first()
        )
        if session is None:
            title = message.strip()[:60] if message.strip() else "Chat baru"
            session = BotSession(id=session_uuid, user_id=user.id, title=title)
            db.add(session)
            db.commit()
            db.refresh(session)
    return session


def _get_user_session(db: Session, user: User, session_id_str: str) -> BotSession | None:
    """Retrieve an existing bot session owned by user by UUID or alias string."""
    session = None
    try:
        raw_uuid = uuid_module.UUID(session_id_str)
        session = (
            db.query(BotSession)
            .filter(BotSession.id == raw_uuid, BotSession.user_id == user.id)
            .first()
        )
    except (ValueError, AttributeError):
        pass

    if session is None:
        session_uuid = _resolve_session_uuid(user, session_id_str)
        session = (
            db.query(BotSession)
            .filter(BotSession.id == session_uuid, BotSession.user_id == user.id)
            .first()
        )

    return session


@router.post("", summary="Chat with Agentic Bot (SSE streaming)")
@router.post("/", include_in_schema=False)
def chat_bot_endpoint(payload: BotIn, user: User = Depends(get_current_user)):
    """Free-form agentic AI chatbot endpoint using LangGraph and ChromaDB RAG.
    Streams response events via Server-Sent Events (SSE).
    """

    def event_stream():
        db = SessionLocal()
        final_text_parts: list[str] = []
        try:
            session = _get_or_create_session(db, user, payload.session_id, payload.message)

            # Persist incoming user message
            user_msg = BotMessage(
                session_id=session.id,
                role="user",
                content=payload.message,
            )
            db.add(user_msg)

            if session.title == "Chat baru" and payload.message.strip():
                session.title = payload.message.strip()[:60]

            session.updated_at = datetime.now(timezone.utc)
            db.commit()

            # Retrieve sliding window of up to 20 previous messages (excluding current message)
            history_rows = (
                db.query(BotMessage)
                .filter(BotMessage.session_id == session.id, BotMessage.id != user_msg.id)
                .order_by(BotMessage.created_at.desc())
                .limit(20)
                .all()
            )
            history_rows.reverse()

            history = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "tool_name": msg.tool_name,
                    "tool_call_id": msg.tool_call_id,
                }
                for msg in history_rows
            ]

            generator = run_bot_agent(
                db=db,
                user_message=payload.message,
                history=history,
                session_obj=session,
            )

            for event in generator:
                yield _sse(event)
                event_type = event.get("type")
                if event_type == "text":
                    final_text_parts.append(event.get("delta") or "")
                elif event_type == "needs_input":
                    final_text_parts.append(event.get("message") or "")

            final_content = "".join(final_text_parts).strip()
            if final_content:
                assistant_msg = BotMessage(
                    session_id=session.id,
                    role="assistant",
                    content=final_content,
                )
                db.add(assistant_msg)
                session.updated_at = datetime.now(timezone.utc)
                db.commit()

        except Exception as exc:
            logger.exception("chat_bot_endpoint: event_stream error")
            yield _sse({"type": "error", "message": f"Terjadi kesalahan: {exc}"})
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions", response_model=list[BotSessionOut], summary="List user bot sessions")
def list_bot_sessions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all bot sessions belonging to the current user ordered by updated_at descending."""
    sessions = (
        db.query(BotSession)
        .filter(BotSession.user_id == user.id)
        .order_by(BotSession.updated_at.desc())
        .all()
    )
    return sessions


@router.get(
    "/sessions/{session_id}",
    response_model=BotSessionDetailOut,
    summary="Get bot session detail with messages",
)
def get_bot_session_detail(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieve full details of a specific bot session including its messages."""
    session = _get_user_session(db, user, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Bot session not found"
        )

    messages = (
        db.query(BotMessage)
        .filter(BotMessage.session_id == session.id)
        .order_by(BotMessage.created_at.asc())
        .all()
    )
    return BotSessionDetailOut(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        machine_id=session.machine_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=messages,
    )


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[BotMessageOut],
    summary="Get messages for a bot session",
)
def get_bot_session_messages(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieve all messages belonging to a specific bot session."""
    session = _get_user_session(db, user, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Bot session not found"
        )

    messages = (
        db.query(BotMessage)
        .filter(BotMessage.session_id == session.id)
        .order_by(BotMessage.created_at.asc())
        .all()
    )
    return messages


@router.delete("/sessions/{session_id}", summary="Delete a bot session")
def delete_bot_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a bot session and its associated messages."""
    session = _get_user_session(db, user, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Bot session not found"
        )

    db.delete(session)
    db.commit()
    return {"status": "ok", "message": "Bot session deleted successfully"}
