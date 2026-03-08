"""Add osm_id column and spatial index to stores.

Supports bulk import of store locations from OpenStreetMap.
- osm_id BIGINT UNIQUE for deduplication on re-import
- Composite index on (lat, lon) for bounding-box queries

Existing stores keep osm_id = NULL.

Revision ID: 024
Revises: 023
"""

from alembic import op
import sqlalchemy as sa

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stores",
        sa.Column("osm_id", sa.BigInteger(), unique=True, nullable=True),
    )
    op.create_index(
        "idx_stores_lat_lon", "stores", ["lat", "lon"]
    )


def downgrade() -> None:
    op.drop_index("idx_stores_lat_lon", table_name="stores")
    op.drop_column("stores", "osm_id")
