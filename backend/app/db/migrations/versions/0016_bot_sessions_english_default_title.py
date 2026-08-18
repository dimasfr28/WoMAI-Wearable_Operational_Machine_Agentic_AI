"""bot_sessions.title default translated to English ("Chat baru" -> "New
Chat") — part of the site-wide "no more Indonesian" sweep; matches
chat_sessions.title's existing English default. Backfills any existing rows
still sitting on the untouched Indonesian default so old sessions a user
never renamed don't keep showing Indonesian text either.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("bot_sessions", "title", server_default="New Chat")
    op.execute("UPDATE bot_sessions SET title = 'New Chat' WHERE title = 'Chat baru'")


def downgrade() -> None:
    op.execute("UPDATE bot_sessions SET title = 'Chat baru' WHERE title = 'New Chat'")
    op.alter_column("bot_sessions", "title", server_default="Chat baru")
