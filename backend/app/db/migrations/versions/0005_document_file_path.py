"""add documents.file_path — PDF uploads are now persisted to disk under the
host-mounted /data/pdf_library directory (/home/dimas/comfest/document on the
host) instead of being parsed-then-discarded, so uploaded files survive
container restarts and existing library PDFs can be migrated in place. This
column stores the path relative to that directory (just the filename in
practice, since uploads land flat in the library root).

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("file_path", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "file_path")
