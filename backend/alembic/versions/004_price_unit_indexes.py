"""Add unit_reference column and price/history indexes to offers

Revision ID: 004
Revises: 003
Create Date: 2026-03-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "offers",
        sa.Column("unit_reference", sa.String(20), nullable=True),
    )
    op.create_index(
        "idx_offers_product_valid_from",
        "offers",
        ["product_id", "valid_from"],
    )
    op.create_index(
        "idx_offers_price_per_unit_notnull",
        "offers",
        ["price_per_unit"],
        postgresql_where=sa.text("price_per_unit IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_offers_price_per_unit_notnull", table_name="offers")
    op.drop_index("idx_offers_product_valid_from", table_name="offers")
    op.drop_column("offers", "unit_reference")
