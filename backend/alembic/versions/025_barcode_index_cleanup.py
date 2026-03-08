"""Add barcode index and clean up invalid barcode data.

Revision ID: 025
Revises: 024
Create Date: 2026-03-08
"""

import sqlalchemy as sa
from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. NULL out non-EAN barcodes (Esselunga internal codes, etc.)
    op.execute(
        """
        UPDATE products
        SET barcode = NULL
        WHERE barcode IS NOT NULL
          AND (
            barcode !~ '^[0-9]+$'
            OR length(barcode) NOT IN (8, 13)
          )
        """
    )

    # 2. Create partial index on valid barcodes (NOT unique — some existing
    #    duplicates may share a barcode; the dedup logic will merge over time)
    op.create_index(
        "ix_products_barcode",
        "products",
        ["barcode"],
        unique=False,
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_products_barcode", table_name="products")
