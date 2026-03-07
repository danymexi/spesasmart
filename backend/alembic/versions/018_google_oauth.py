"""018 – Add auth_provider and google_id to user_profiles.

Revision ID: 018
Revises: 017
Create Date: 2026-03-07
"""

import sqlalchemy as sa
from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("auth_provider", sa.String(20), server_default="local", nullable=False),
    )
    op.add_column(
        "user_profiles",
        sa.Column("google_id", sa.String(100), nullable=True, unique=True),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "google_id")
    op.drop_column("user_profiles", "auth_provider")
