"""Add multiple shopping lists support and user search_radius_km.

Creates shopping_lists table for grouping items into named lists.
Adds list_id FK to shopping_list_items (nullable for backward compat).
Adds search_radius_km to user_profiles.

Revision ID: 015
Revises: 014
Create Date: 2026-03-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create shopping_lists table
    op.create_table(
        "shopping_lists",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, server_default="La mia lista"),
        sa.Column("emoji", sa.String(10), server_default="🛒"),
        sa.Column("is_archived", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_shopping_lists_user", "shopping_lists", ["user_id"])

    # Add list_id to shopping_list_items (nullable for backward compat)
    op.add_column(
        "shopping_list_items",
        sa.Column("list_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("shopping_lists.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("idx_sli_list_id", "shopping_list_items", ["list_id"])

    # Add search_radius_km to user_profiles
    op.add_column(
        "user_profiles",
        sa.Column("search_radius_km", sa.Integer, server_default="20"),
    )

    # Migrate existing items: create a default list per user and link items
    op.execute("""
        INSERT INTO shopping_lists (user_id, name, emoji)
        SELECT DISTINCT user_id, 'La mia lista', '🛒'
        FROM shopping_list_items
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        UPDATE shopping_list_items sli
        SET list_id = sl.id
        FROM shopping_lists sl
        WHERE sli.user_id = sl.user_id
          AND sli.list_id IS NULL
    """)


def downgrade() -> None:
    op.drop_column("user_profiles", "search_radius_km")
    op.drop_index("idx_sli_list_id", "shopping_list_items")
    op.drop_column("shopping_list_items", "list_id")
    op.drop_index("idx_shopping_lists_user", "shopping_lists")
    op.drop_table("shopping_lists")
