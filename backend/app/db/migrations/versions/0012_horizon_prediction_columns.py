"""predictions: add horizon model columns (rancangan.txt Section 5,
"Probability Failure in +10 Minute") — a separate model/question from the
main predicted_label/failure_probability columns, computed once per reading
in the same pipeline and stored alongside.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("predictions", sa.Column("horizon_predicted_label", sa.Boolean(), nullable=True))
    op.add_column("predictions", sa.Column("horizon_failure_probability", sa.Numeric(5, 4), nullable=True))
    op.add_column("predictions", sa.Column("horizon_model_version", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("predictions", "horizon_model_version")
    op.drop_column("predictions", "horizon_failure_probability")
    op.drop_column("predictions", "horizon_predicted_label")
