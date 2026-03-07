"""017 – Add is_guest flag to user_profiles.

Revision ID: 017
Revises: 016
Create Date: 2026-03-07
"""

import sqlalchemy as sa
from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("is_guest", sa.Boolean, server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "is_guest")
