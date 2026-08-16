"""add ai_explanation/recommended_action columns to final_reports — backs the
Early Warning card's "AI Diagnosis"/"Recommended Action" sections on the
frontend /report page. Generated once per report (same lifecycle as
report_text) inside _run_report_pipeline(), never on the GET /report/latest
read path — see backend/app/rag/final_report.py's generate_early_warning_narrative().

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-14

Renumbered from 0011 to 0015 on 2026-08-16: this migration and
0011_bot_tables.py (a separate branch's work, merged later) both independently
claimed revision id "0011" against down_revision "0010" — a genuine collision
(Alembic's revision map is keyed by id, so two files sharing one id is
invalid, not just a normal two-head branch). The two migrations touch
disjoint tables (this one: final_reports columns; bot_tables: new
bot_sessions/bot_messages tables), so there's no ordering dependency between
them — this one was simply moved to the end of the chain (after 0014, the
other branch's last migration) rather than renumbering anyone else's work.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("final_reports", sa.Column("ai_explanation", sa.Text(), nullable=True))
    op.add_column("final_reports", sa.Column("recommended_action", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("final_reports", "recommended_action")
    op.drop_column("final_reports", "ai_explanation")
