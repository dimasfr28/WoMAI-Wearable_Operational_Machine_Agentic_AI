"""Backfill: create the first machine ("Haas Milling Machine 2023") and assign
every pre-existing sensor_runs/documents row to it. Before multi-machine
support, the whole system implicitly assumed a single machine — this migration
makes that assumption explicit as real data instead of leaving those rows with
machine_id=NULL (which would make them invisible once every read path filters
by machine_id).

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-09

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_MACHINE_NAME = "Haas Milling Machine 2023"


def upgrade() -> None:
    conn = op.get_bind()

    existing = conn.execute(
        sa.text("SELECT id FROM machines WHERE name = :name"), {"name": DEFAULT_MACHINE_NAME}
    ).fetchone()
    if existing:
        machine_id = existing[0]
    else:
        machine_id = uuid.uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO machines (id, name, machine_type, created_at) "
                "VALUES (:id, :name, :machine_type, now())"
            ),
            {"id": machine_id, "name": DEFAULT_MACHINE_NAME, "machine_type": "Haas"},
        )

    conn.execute(
        sa.text("UPDATE sensor_runs SET machine_id = :mid WHERE machine_id IS NULL"),
        {"mid": machine_id},
    )
    conn.execute(
        sa.text("UPDATE documents SET machine_id = :mid WHERE machine_id IS NULL"),
        {"mid": machine_id},
    )


def downgrade() -> None:
    # Intentionally a no-op: unsetting machine_id on backfilled rows would
    # just recreate the pre-migration NULL state, which downgrade()'s caller
    # (0007's downgrade, dropping the column entirely) already handles.
    pass
