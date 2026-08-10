"""add part_price_lookups.price_min/price_max — the links returned by e-commerce
search are catalog/listing pages containing many products at once (e.g. an
Alibaba/Tokopedia search results page), not a single product page. A single
`price` column meant taking the first regex match on the page, which was
frequently irrelevant or None (many e-commerce pages block scraping bots
outright). Extracting every price mentioned in a listing and reporting a
min-max range across 2-3 sampled products is more representative of the
actual cost. `price` is kept (nullable) for backward compatibility with any
existing rows/readers; new lookups populate price_min/price_max instead.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("part_price_lookups", sa.Column("price_min", sa.Numeric(12, 2), nullable=True))
    op.add_column("part_price_lookups", sa.Column("price_max", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("part_price_lookups", "price_max")
    op.drop_column("part_price_lookups", "price_min")
