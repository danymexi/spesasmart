"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Chains
    op.create_table(
        "chains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(50), unique=True, nullable=False),
        sa.Column("logo_url", sa.Text()),
        sa.Column("website_url", sa.Text()),
    )

    # Stores
    op.create_table(
        "stores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("chain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chains.id")),
        sa.Column("name", sa.String(200)),
        sa.Column("address", sa.Text()),
        sa.Column("city", sa.String(100)),
        sa.Column("province", sa.String(10), server_default="MB"),
        sa.Column("zip_code", sa.String(10)),
        sa.Column("lat", sa.Numeric(10, 7)),
        sa.Column("lon", sa.Numeric(10, 7)),
    )

    # Flyers
    op.create_table(
        "flyers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("chain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chains.id")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stores.id"), nullable=True),
        sa.Column("title", sa.String(300)),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("pages_count", sa.Integer()),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Flyer pages
    op.create_table(
        "flyer_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("flyer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("flyers.id")),
        sa.Column("page_number", sa.Integer()),
        sa.Column("image_url", sa.Text()),
        sa.Column("ocr_raw_text", sa.Text()),
        sa.Column("processed", sa.Boolean(), server_default=sa.text("false")),
    )

    # Products
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("brand", sa.String(200)),
        sa.Column("category", sa.String(100)),
        sa.Column("subcategory", sa.String(100)),
        sa.Column("unit", sa.String(50)),
        sa.Column("barcode", sa.String(50)),
        sa.Column("image_url", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Offers
    op.create_table(
        "offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id")),
        sa.Column("flyer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("flyers.id")),
        sa.Column("chain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chains.id")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stores.id"), nullable=True),
        sa.Column("original_price", sa.Numeric(8, 2)),
        sa.Column("offer_price", sa.Numeric(8, 2), nullable=False),
        sa.Column("discount_pct", sa.Numeric(5, 2)),
        sa.Column("discount_type", sa.String(50)),
        sa.Column("quantity", sa.String(100)),
        sa.Column("price_per_unit", sa.Numeric(8, 2)),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_to", sa.Date()),
        sa.Column("raw_text", sa.Text()),
        sa.Column("confidence", sa.Numeric(3, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indices on offers
    op.create_index("idx_offers_product", "offers", ["product_id"])
    op.create_index("idx_offers_chain", "offers", ["chain_id"])
    op.create_index("idx_offers_dates", "offers", ["valid_from", "valid_to"])
    op.create_index("idx_offers_price", "offers", ["offer_price"])

    # User profiles
    op.create_table(
        "user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("telegram_chat_id", sa.BigInteger()),
        sa.Column("push_token", sa.Text()),
        sa.Column("preferred_zone", sa.String(100), server_default="Monza e Brianza"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # User watchlist
    op.create_table(
        "user_watchlist",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_profiles.id")),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id")),
        sa.Column("target_price", sa.Numeric(8, 2)),
        sa.Column("notify_any_offer", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "product_id", name="uq_user_product"),
    )

    # User stores
    op.create_table(
        "user_stores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_profiles.id")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stores.id")),
        sa.UniqueConstraint("user_id", "store_id", name="uq_user_store"),
    )


def downgrade() -> None:
    op.drop_table("user_stores")
    op.drop_table("user_watchlist")
    op.drop_table("user_profiles")
    op.drop_index("idx_offers_price", "offers")
    op.drop_index("idx_offers_dates", "offers")
    op.drop_index("idx_offers_chain", "offers")
    op.drop_index("idx_offers_product", "offers")
    op.drop_table("offers")
    op.drop_table("products")
    op.drop_table("flyer_pages")
    op.drop_table("flyers")
    op.drop_table("stores")
    op.drop_table("chains")
