"""Add session-based fields to supermarket_credentials.

Makes encrypted_email and encrypted_password nullable (no longer required
when using session-based auth). Adds encrypted_session and session_expires_at.

Revision ID: 014
Revises: 013
Create Date: 2026-03-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make email/password nullable (session-based auth doesn't need them)
    op.alter_column(
        "supermarket_credentials",
        "encrypted_email",
        existing_type=sa.Text,
        nullable=True,
    )
    op.alter_column(
        "supermarket_credentials",
        "encrypted_password",
        existing_type=sa.Text,
        nullable=True,
    )

    # Add session fields
    op.add_column(
        "supermarket_credentials",
        sa.Column("encrypted_session", sa.Text, nullable=True),
    )
    op.add_column(
        "supermarket_credentials",
        sa.Column("session_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("supermarket_credentials", "session_expires_at")
    op.drop_column("supermarket_credentials", "encrypted_session")

    op.alter_column(
        "supermarket_credentials",
        "encrypted_password",
        existing_type=sa.Text,
        nullable=False,
    )
    op.alter_column(
        "supermarket_credentials",
        "encrypted_email",
        existing_type=sa.Text,
        nullable=False,
    )
