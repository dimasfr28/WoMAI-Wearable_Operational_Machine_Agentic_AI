"""sensor_runs.document_id FK: add ON DELETE SET NULL — deleting a Document via
DELETE /knowledgebase/documents/{id} was failing with a raw 500 ForeignKeyViolation
whenever a SensorRun still referenced it (set by _close_run_and_build_chunk when a
real-time run closes and generates its own chunk Document). The run and its
readings/predictions are independent of the document that summarized it, so on
delete the link should just clear, not block the delete.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("sensor_runs_document_id_fkey", "sensor_runs", type_="foreignkey")
    op.create_foreign_key(
        "sensor_runs_document_id_fkey",
        "sensor_runs",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("sensor_runs_document_id_fkey", "sensor_runs", type_="foreignkey")
    op.create_foreign_key(
        "sensor_runs_document_id_fkey",
        "sensor_runs",
        "documents",
        ["document_id"],
        ["id"],
    )
