"""final_reports: add cause_analysis_short + suggestion_general (rancangan.txt
Section 5, "AI Explanation" panel on Machine Diagnosis) — Cause Analysis LLM
(short root-cause summary, max 1 sentence/40 words, 1 part) and Suggestions
for Improvement LLM (general/non-numeric adjustment wording), both generated
once alongside report_text.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("final_reports", sa.Column("cause_analysis_short", sa.Text(), nullable=True))
    op.add_column("final_reports", sa.Column("suggestion_general", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("final_reports", "suggestion_general")
    op.drop_column("final_reports", "cause_analysis_short")
