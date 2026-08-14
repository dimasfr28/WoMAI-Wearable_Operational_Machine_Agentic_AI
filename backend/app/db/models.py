"""SQLAlchemy models — mirrors Section 4 of RANCANGAN_SISTEM.md exactly.

Includes chat_sessions / chat_messages / agent_tool_logs (Section 4.5) as models
only, per the explicit scope note in the design doc: routes_chat.py and
ChatbotPage.jsx are NOT implemented in this phase, but the tables/migrations
are prepared now so no further migration is needed later.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def gen_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# 4.1 User & Role
# ---------------------------------------------------------------------------

UserRole = Enum("admin", "engineer", "viewer", name="user_role")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    role: Mapped[str] = mapped_column(UserRole, nullable=False, server_default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# 4.1b Machine — multi-machine support: one user account can monitor more than
# one physical machine, each with its own sensor history, documents, and
# reports. Introduced after the system had been built assuming a single
# implicit machine; SensorRun and Document both carry machine_id so every
# other table (SensorReading via run_id, Prediction/Shap/etc. via
# sensor_reading_id chains) is scoped to a machine transitively.
# ---------------------------------------------------------------------------


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    machine_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Operational status (running/stopped/etc). Hardcoded to "running" for every
    # machine for now (migration 0009) — there's no real-time PLC/OPC-UA feed or
    # heartbeat signal wired up yet to derive this from actual machine state, so
    # it's a placeholder column rather than a computed value. Revisit once a
    # real status source exists.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="running")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# 4.2 Knowledgebase (Dokumen & Chunk)
# ---------------------------------------------------------------------------

DocumentSourceType = Enum("pdf", "sensor_numeric", name="document_source_type")
DocumentStatus = Enum("processing", "completed", "rejected_duplicate", "failed", name="document_status")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    machine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("machines.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_type: Mapped[str] = mapped_column(DocumentSourceType, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    doc_name: Mapped[str] = mapped_column(String(255), nullable=False)
    machine_type: Mapped[str | None] = mapped_column(String(50), server_default="Haas")
    status: Mapped[str] = mapped_column(DocumentStatus, nullable=False, server_default="processing")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    heading_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chroma_id: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(
        String(150), nullable=False, server_default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship(back_populates="chunks")


# ---------------------------------------------------------------------------
# 4.3 Data Sensor & Run
# ---------------------------------------------------------------------------


class SensorRun(Base):
    __tablename__ = "sensor_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    machine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("machines.id", ondelete="CASCADE"), nullable=True, index=True
    )
    run_label: Mapped[str] = mapped_column(String(50), nullable=False)
    start_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sensor_runs.id"), nullable=True, index=True
    )
    reading_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    air_temperature_k: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    process_temperature_k: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    rotational_speed_rpm: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_wear_min: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    machine_failure: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    input_source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="manual_form")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# 4.4 Prediksi, SHAP, Rekomendasi, RAG, Harga Part
# ---------------------------------------------------------------------------


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    sensor_reading_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sensor_readings.id"), nullable=False
    )
    predicted_label: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_probability: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    # SHAP TreeExplainer expected_value (base_value) for this prediction — persisted
    # so GET /report/latest can reconstruct ShapExplanationOut.base_value purely from
    # the DB (no re-running SHAP). Nullable for rows predating this column.
    shap_base_value: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShapExplanation(Base):
    __tablename__ = "shap_explanations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    prediction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False
    )
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_value: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    shap_value: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    prediction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False
    )
    recommendation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RootCauseAnalysis(Base):
    __tablename__ = "root_cause_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    prediction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False
    )
    rag_query: Mapped[str] = mapped_column(Text, nullable=False)
    rag_answer: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_chunk_ids: Mapped[list] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}")
    used_web_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PartPriceLookup(Base):
    __tablename__ = "part_price_lookups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    prediction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False
    )
    part_name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_min: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_max: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), server_default="IDR")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FinalReport(Base):
    __tablename__ = "final_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    prediction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False
    )
    report_text: Mapped[str] = mapped_column(Text, nullable=False)
    llm_model: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# 4.5 Chatbot (schema prepared now — routes/page NOT implemented this phase)
# ---------------------------------------------------------------------------


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, server_default="New Chat")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


ChatRole = Enum("user", "assistant", "system", "tool", name="chat_role")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(ChatRole, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentToolLog(Base):
    __tablename__ = "agent_tool_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=True
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# SOP library (2026-08-13) — standalone structured procedure library, not
# tied to a failure-mode taxonomy or a specific machine.
# ---------------------------------------------------------------------------


class Sop(Base):
    __tablename__ = "sops"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    symptoms: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    reference: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Bot Session & Messages (/bot chatbot)
# ---------------------------------------------------------------------------

BotRole = Enum("user", "assistant", "tool", name="bot_message_role")


class BotSession(Base):
    __tablename__ = "bot_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, server_default="Chat baru")
    machine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("machines.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BotMessage(Base):
    __tablename__ = "bot_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bot_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(BotRole, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

