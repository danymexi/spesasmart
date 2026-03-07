"""Multiple shopping lists with sharing support.

Creates a ``shopping_lists`` table so each user can have many named lists.
Adds ``list_id`` and ``sort_order`` to ``shopping_list_items``, then migrates
existing items into a default list per user.

Revision ID: 015
Revises: 014
Create Date: 2026-03-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create shopping_lists table
    op.create_table(
        "shopping_lists",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, server_default="Spesa"),
        sa.Column("emoji", sa.String(10), nullable=True),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_template", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("share_token", sa.String(64), nullable=True, unique=True),
        sa.Column("share_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_shopping_lists_user_id", "shopping_lists", ["user_id"])

    # 2. Add list_id (nullable first) and sort_order to shopping_list_items
    op.add_column(
        "shopping_list_items",
        sa.Column("list_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "shopping_list_items",
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
    )

    # 3. Data migration: create a default "Spesa" list per user and link items
    op.execute(
        """
        INSERT INTO shopping_lists (id, user_id, name, sort_order)
        SELECT gen_random_uuid(), user_id, 'Spesa', 0
        FROM (SELECT DISTINCT user_id FROM shopping_list_items) sub
        """
    )
    op.execute(
        """
        UPDATE shopping_list_items
        SET list_id = sl.id
        FROM shopping_lists sl
        WHERE shopping_list_items.user_id = sl.user_id
          AND shopping_list_items.list_id IS NULL
        """
    )

    # 4. Now make list_id NOT NULL and add FK
    op.alter_column("shopping_list_items", "list_id", nullable=False)
    op.create_foreign_key(
        "fk_shopping_list_items_list_id",
        "shopping_list_items",
        "shopping_lists",
        ["list_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_shopping_list_items_list_id", "shopping_list_items", ["list_id"])


def downgrade() -> None:
    op.drop_index("ix_shopping_list_items_list_id", table_name="shopping_list_items")
    op.drop_constraint("fk_shopping_list_items_list_id", "shopping_list_items", type_="foreignkey")
    op.drop_column("shopping_list_items", "sort_order")
    op.drop_column("shopping_list_items", "list_id")
    op.drop_index("ix_shopping_lists_user_id", table_name="shopping_lists")
    op.drop_table("shopping_lists")
