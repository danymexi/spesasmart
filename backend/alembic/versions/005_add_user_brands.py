"""Add user_brands table for favourite brands tracking

Revision ID: 005
Revises: 004
Create Date: 2026-03-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_brands",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("notify", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "brand_name", name="uq_user_brand"),
    )
    op.create_index("idx_user_brands_user_id", "user_brands", ["user_id"])
    op.create_index("idx_user_brands_brand_name", "user_brands", ["brand_name"])


def downgrade() -> None:
    op.drop_index("idx_user_brands_brand_name", table_name="user_brands")
    op.drop_index("idx_user_brands_user_id", table_name="user_brands")
    op.drop_table("user_brands")
