"""add machines.status — placeholder operational status column, hardcoded to
"running" for every machine (both existing and new) since there is no
real-time PLC/OPC-UA feed or heartbeat signal wired up yet to derive this from
actual machine state. Revisit once a real status source exists.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "machines",
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
    )


def downgrade() -> None:
    op.drop_column("machines", "status")
