"""v1.2 enhancements: preferred_chains, ppu_computed flag, performance indices

Revision ID: 009
Revises: 008
Create Date: 2026-03-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # preferred_chains on user_profiles (JSON array stored as string)
    op.add_column(
        "user_profiles",
        sa.Column("preferred_chains", sa.String(200), nullable=True),
    )

    # Flag to distinguish extracted vs computed price_per_unit
    op.add_column(
        "offers",
        sa.Column(
            "ppu_computed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    # Performance indices for cross-chain comparison queries
    op.create_index(
        "ix_offers_product_validity",
        "offers",
        ["product_id", "valid_from", "valid_to"],
    )
    op.create_index(
        "ix_offers_ppu",
        "offers",
        ["price_per_unit"],
        postgresql_where=sa.text("price_per_unit IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_offers_ppu", table_name="offers")
    op.drop_index("ix_offers_product_validity", table_name="offers")
    op.drop_column("offers", "ppu_computed")
    op.drop_column("user_profiles", "preferred_chains")
