"""machine_reports table (rancangan.txt Section 7, "Machine Report") — one row
per generated formal PDF report, stored on disk under a per-day folder scheme,
referenced here by relative path.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "machine_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "machine_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("machines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("predictions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("report_number", sa.String(50), nullable=False, unique=True),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("operating_status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_machine_reports_machine_id", "machine_reports", ["machine_id"])


def downgrade() -> None:
    op.drop_index("idx_machine_reports_machine_id", table_name="machine_reports")
    op.drop_table("machine_reports")
