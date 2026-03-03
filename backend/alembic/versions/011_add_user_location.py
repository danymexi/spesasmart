"""Add lat/lon columns to user_profiles for geolocation

Revision ID: 011
Revises: 010
Create Date: 2026-03-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("lat", sa.Numeric(10, 7), nullable=True))
    op.add_column("user_profiles", sa.Column("lon", sa.Numeric(10, 7), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "lon")
    op.drop_column("user_profiles", "lat")
