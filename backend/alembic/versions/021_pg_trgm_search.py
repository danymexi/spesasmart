"""Enable pg_trgm extension and add GIN indexes for fuzzy search.

Revision ID: 021
Revises: 020
"""

from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pg_trgm extension for fuzzy text search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # GIN indexes on product name and brand for similarity search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_products_name_trgm "
        "ON products USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_products_brand_trgm "
        "ON products USING gin (brand gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_products_brand_trgm")
    op.execute("DROP INDEX IF EXISTS ix_products_name_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
