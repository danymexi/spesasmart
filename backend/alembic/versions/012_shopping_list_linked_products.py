"""Add shopping_list_item_products junction table for multi-product selection

Revision ID: 012
Revises: 011
Create Date: 2026-03-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shopping_list_item_products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("item_id", UUID(as_uuid=True), sa.ForeignKey("shopping_list_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("item_id", "product_id", name="uq_slp_item_product"),
    )
    op.create_index("idx_slp_item_id", "shopping_list_item_products", ["item_id"])
    op.create_index("idx_slp_product_id", "shopping_list_item_products", ["product_id"])


def downgrade() -> None:
    op.drop_index("idx_slp_product_id", table_name="shopping_list_item_products")
    op.drop_index("idx_slp_item_id", table_name="shopping_list_item_products")
    op.drop_table("shopping_list_item_products")
