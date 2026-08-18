"""machine_reports: add run_id (one report row per sensor_runs row instead of
per reading) and updated_at — see
docs/superpowers/specs/2026-08-18-run-clustering-and-report-design.md.

Nullable + unique: historical rows predating this column keep run_id=NULL,
any number of which are allowed by the unique index (NULL is never "equal"
to another NULL in a unique constraint, in PostgreSQL as in SQLite) — every
row created going forward always has run_id set.

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "machine_reports",
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sensor_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_machine_reports_run_id", "machine_reports", ["run_id"], unique=True)
    op.add_column(
        "machine_reports",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_column("machine_reports", "updated_at")
    op.drop_index("ix_machine_reports_run_id", table_name="machine_reports")
    op.drop_column("machine_reports", "run_id")
