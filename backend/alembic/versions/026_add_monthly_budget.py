"""Add monthly_budget column to user_profiles.

Revision ID: 026
Revises: 025
Create Date: 2026-03-08
"""

import sqlalchemy as sa
from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("monthly_budget", sa.Numeric(8, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "monthly_budget")
