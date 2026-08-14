"""add bot_sessions and bot_messages tables

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

bot_role_enum = postgresql.ENUM("user", "assistant", "tool", name="bot_message_role", create_type=False)


def upgrade() -> None:
    bot_role_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "bot_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False, server_default="Chat baru"),
        sa.Column("machine_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("machines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_bot_sessions_user_id", "bot_sessions", ["user_id"])

    op.create_table(
        "bot_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bot_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", bot_role_enum, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=True),
        sa.Column("tool_call_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_bot_messages_session_id", "bot_messages", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_bot_messages_session_id", table_name="bot_messages")
    op.drop_table("bot_messages")
    op.drop_index("ix_bot_sessions_user_id", table_name="bot_sessions")
    op.drop_table("bot_sessions")
    bot_role_enum.drop(op.get_bind(), checkfirst=True)
