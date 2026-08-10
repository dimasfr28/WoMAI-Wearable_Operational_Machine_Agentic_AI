"""Multi-machine support — one user account can monitor more than one physical
machine. Adds a `machines` table plus `machine_id` on `sensor_runs` and
`documents` (both nullable at the schema level so existing rows don't need a
value yet; 0008 backfills them into a single "Haas Milling Machine 2023" row
and the app-level contract going forward is that every NEW row always sets
machine_id explicitly). SensorReading/Prediction/etc. are scoped to a machine
transitively via sensor_runs.machine_id — no direct column needed there.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "machines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("machine_type", sa.String(50), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.add_column(
        "sensor_runs",
        sa.Column("machine_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("machines.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_sensor_runs_machine_id", "sensor_runs", ["machine_id"])

    op.add_column(
        "documents",
        sa.Column("machine_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("machines.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_documents_machine_id", "documents", ["machine_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_machine_id", table_name="documents")
    op.drop_column("documents", "machine_id")
    op.drop_index("ix_sensor_runs_machine_id", table_name="sensor_runs")
    op.drop_column("sensor_runs", "machine_id")
    op.drop_table("machines")
