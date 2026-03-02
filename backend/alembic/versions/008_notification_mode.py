"""Add notification_mode to user_profiles (instant or digest)

Revision ID: 008
Revises: 007
Create Date: 2026-03-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column(
            "notification_mode",
            sa.String(20),
            server_default=sa.text("'instant'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "notification_mode")
