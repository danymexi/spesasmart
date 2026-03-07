"""019 – Add is_admin flag to user_profiles.

Revision ID: 019
Revises: 018
Create Date: 2026-03-07
"""

import sqlalchemy as sa
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("is_admin", sa.Boolean, server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "is_admin")
