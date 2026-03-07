"""Add phone, opening_hours, website_url to stores.

Revision ID: 020
Revises: 019
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stores", sa.Column("phone", sa.String(30), nullable=True))
    op.add_column("stores", sa.Column("opening_hours", JSONB, nullable=True))
    op.add_column("stores", sa.Column("website_url", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("stores", "website_url")
    op.drop_column("stores", "opening_hours")
    op.drop_column("stores", "phone")
