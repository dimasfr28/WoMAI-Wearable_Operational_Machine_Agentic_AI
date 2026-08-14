"""add ai_explanation/recommended_action columns to final_reports — backs the
Early Warning card's "AI Diagnosis"/"Recommended Action" sections on the
frontend /report page. Generated once per report (same lifecycle as
report_text) inside _run_report_pipeline(), never on the GET /report/latest
read path — see backend/app/rag/final_report.py's generate_early_warning_narrative().

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("final_reports", sa.Column("ai_explanation", sa.Text(), nullable=True))
    op.add_column("final_reports", sa.Column("recommended_action", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("final_reports", "recommended_action")
    op.drop_column("final_reports", "ai_explanation")
