"""Add purchase history tables: supermarket_credentials, purchase_orders,
purchase_items, purchase_sync_log.

Revision ID: 013
Revises: 012
Create Date: 2026-03-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- supermarket_credentials --
    op.create_table(
        "supermarket_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chain_slug", sa.String(50), nullable=False),
        sa.Column("encrypted_email", sa.Text, nullable=False),
        sa.Column("encrypted_password", sa.Text, nullable=False),
        sa.Column("is_valid", sa.Boolean, server_default=sa.text("true")),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "chain_slug", name="uq_user_chain_cred"),
    )
    op.create_index("idx_cred_user_id", "supermarket_credentials", ["user_id"])

    # -- purchase_orders --
    op.create_table(
        "purchase_orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chain_slug", sa.String(50), nullable=False),
        sa.Column("external_order_id", sa.String(100), nullable=False),
        sa.Column("order_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("store_name", sa.String(200), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("raw_data", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "chain_slug", "external_order_id", name="uq_user_chain_order"),
    )
    op.create_index("idx_po_user_id", "purchase_orders", ["user_id"])
    op.create_index("idx_po_order_date", "purchase_orders", ["order_date"])

    # -- purchase_items --
    op.create_table(
        "purchase_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_id", UUID(as_uuid=True), sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("external_name", sa.String(300), nullable=False),
        sa.Column("external_code", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=True),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("brand", sa.String(200), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_pi_order_id", "purchase_items", ["order_id"])
    op.create_index("idx_pi_product_id", "purchase_items", ["product_id"])

    # -- purchase_sync_log --
    op.create_table(
        "purchase_sync_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chain_slug", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), server_default=sa.text("'running'")),
        sa.Column("orders_fetched", sa.Integer, server_default=sa.text("0")),
        sa.Column("items_fetched", sa.Integer, server_default=sa.text("0")),
        sa.Column("items_matched", sa.Integer, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index("idx_psl_user_id", "purchase_sync_log", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_psl_user_id", table_name="purchase_sync_log")
    op.drop_table("purchase_sync_log")
    op.drop_index("idx_pi_product_id", table_name="purchase_items")
    op.drop_index("idx_pi_order_id", table_name="purchase_items")
    op.drop_table("purchase_items")
    op.drop_index("idx_po_order_date", table_name="purchase_orders")
    op.drop_index("idx_po_user_id", table_name="purchase_orders")
    op.drop_table("purchase_orders")
    op.drop_index("idx_cred_user_id", table_name="supermarket_credentials")
    op.drop_table("supermarket_credentials")
