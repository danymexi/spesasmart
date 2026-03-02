"""Add shopping_list_items table

Revision ID: 007
Revises: 006
Create Date: 2026-03-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shopping_list_items",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("custom_name", sa.String(300), nullable=True),
        sa.Column("quantity", sa.Integer, server_default=sa.text("1"), nullable=False),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("checked", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("offer_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("offers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_shopping_list_user_id", "shopping_list_items", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_shopping_list_user_id", table_name="shopping_list_items")
    op.drop_table("shopping_list_items")
