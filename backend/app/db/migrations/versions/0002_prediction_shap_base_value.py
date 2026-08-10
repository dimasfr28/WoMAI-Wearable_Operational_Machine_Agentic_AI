"""add predictions.shap_base_value — needed so GET /report/latest can reconstruct
ShapExplanationOut.base_value (SHAP TreeExplainer expected_value) purely from the DB,
without re-running SHAP. Part of the "report generated once at submit time, not on
every GET" refactor.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("shap_base_value", sa.Numeric(10, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("predictions", "shap_base_value")
