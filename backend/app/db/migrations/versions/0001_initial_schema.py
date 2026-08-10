"""initial schema — all Section 4 tables (users, knowledgebase, sensor, predictions, chat)

Revision ID: 0001
Revises:
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # create_type=False on each column-bound ENUM below: the type is created
    # explicitly here (checkfirst=True, idempotent), so create_table()'s
    # automatic before_create type-creation (which does NOT check-first) must
    # be disabled to avoid a duplicate "CREATE TYPE" -> DuplicateObject error.
    user_role = postgresql.ENUM("admin", "engineer", "viewer", name="user_role")
    user_role.create(op.get_bind(), checkfirst=True)
    user_role = postgresql.ENUM("admin", "engineer", "viewer", name="user_role", create_type=False)

    document_source_type = postgresql.ENUM("pdf", "sensor_numeric", name="document_source_type")
    document_source_type.create(op.get_bind(), checkfirst=True)
    document_source_type = postgresql.ENUM("pdf", "sensor_numeric", name="document_source_type", create_type=False)

    document_status = postgresql.ENUM(
        "processing", "completed", "rejected_duplicate", "failed", name="document_status"
    )
    document_status.create(op.get_bind(), checkfirst=True)
    document_status = postgresql.ENUM(
        "processing", "completed", "rejected_duplicate", "failed", name="document_status", create_type=False
    )

    chat_role = postgresql.ENUM("user", "assistant", "system", "tool", name="chat_role")
    chat_role.create(op.get_bind(), checkfirst=True)
    chat_role = postgresql.ENUM("user", "assistant", "system", "tool", name="chat_role", create_type=False)

    # 4.1 Users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=True),
        sa.Column("role", user_role, nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # 4.2 Knowledgebase
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_type", document_source_type, nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("file_sha256", sa.String(64), nullable=True),
        sa.Column("doc_name", sa.String(255), nullable=False),
        sa.Column("machine_type", sa.String(50), server_default="Haas"),
        sa.Column("status", document_status, nullable=False, server_default="processing"),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("heading_1", sa.Text, nullable=True),
        sa.Column("heading_2", sa.Text, nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("chroma_id", sa.String(64), nullable=False),
        sa.Column(
            "embedding_model",
            sa.String(150),
            nullable=False,
            server_default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("document_id", "chunk_index"),
    )
    op.create_index("idx_document_chunks_document_id", "document_chunks", ["document_id"])

    # 4.3 Sensor & Run
    op.create_table(
        "sensor_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_label", sa.String(50), nullable=False),
        sa.Column("start_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_closed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "sensor_readings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sensor_runs.id"), nullable=True),
        sa.Column("reading_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("air_temperature_k", sa.Numeric(6, 2), nullable=False),
        sa.Column("process_temperature_k", sa.Numeric(6, 2), nullable=False),
        sa.Column("rotational_speed_rpm", sa.Integer, nullable=False),
        sa.Column("tool_wear_min", sa.Numeric(6, 2), nullable=False),
        sa.Column("machine_failure", sa.Boolean, nullable=True),
        sa.Column("input_source", sa.String(20), nullable=False, server_default="manual_form"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_sensor_readings_run_id", "sensor_readings", ["run_id"])
    op.create_index(
        "idx_sensor_readings_timestamp", "sensor_readings", ["reading_timestamp"], postgresql_using="btree"
    )

    # 4.4 Prediksi, SHAP, Rekomendasi, RAG, Harga part
    op.create_table(
        "predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "sensor_reading_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sensor_readings.id"), nullable=False
        ),
        sa.Column("predicted_label", sa.Boolean, nullable=False),
        sa.Column("failure_probability", sa.Numeric(5, 4), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "shap_explanations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("predictions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feature_name", sa.String(100), nullable=False),
        sa.Column("feature_value", sa.Numeric(10, 4), nullable=False),
        sa.Column("shap_value", sa.Numeric(10, 6), nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
    )

    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("predictions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recommendation_type", sa.String(30), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "root_cause_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("predictions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rag_query", sa.Text, nullable=False),
        sa.Column("rag_answer", sa.Text, nullable=False),
        sa.Column(
            "retrieved_chunk_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("used_web_fallback", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "part_price_lookups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("predictions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("part_name", sa.String(255), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(10), server_default="IDR"),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "final_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("predictions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("report_text", sa.Text, nullable=False),
        sa.Column("llm_model", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # 4.5 Chatbot (schema only — routes/page not implemented this phase)
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False, server_default="New Chat"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", chat_role, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=True),
        sa.Column("tool_call_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_chat_messages_session_id", "chat_messages", ["session_id", "created_at"])

    op.create_table(
        "agent_tool_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_messages.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("input_payload", postgresql.JSONB, nullable=False),
        sa.Column("output_payload", postgresql.JSONB, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("agent_tool_logs")
    op.drop_index("idx_chat_messages_session_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("final_reports")
    op.drop_table("part_price_lookups")
    op.drop_table("root_cause_analyses")
    op.drop_table("recommendations")
    op.drop_table("shap_explanations")
    op.drop_table("predictions")
    op.drop_index("idx_sensor_readings_timestamp", table_name="sensor_readings")
    op.drop_index("idx_sensor_readings_run_id", table_name="sensor_readings")
    op.drop_table("sensor_readings")
    op.drop_table("sensor_runs")
    op.drop_index("idx_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("users")

    postgresql.ENUM(name="chat_role").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="document_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="document_source_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="user_role").drop(op.get_bind(), checkfirst=True)
