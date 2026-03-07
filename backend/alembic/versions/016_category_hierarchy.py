"""016 – Category hierarchy table.

Revision ID: 016
Revises: 015
Create Date: 2026-03-07
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


# Parent → children mapping based on known Italian grocery categories
CATEGORY_TREE: dict[str, dict] = {
    "Bevande": {"icon": "bottle-soda-classic", "children": ["Acqua", "Succhi", "Bibite", "Birra", "Vino"]},
    "Biscotti": {"icon": "cookie", "children": ["Frollini", "Wafer", "Cracker"]},
    "Carne": {"icon": "food-steak", "children": ["Manzo", "Pollo", "Maiale", "Salumi"]},
    "Cereali": {"icon": "grain", "children": ["Corn Flakes", "Muesli", "Granola"]},
    "Colazione": {"icon": "coffee", "children": ["Caffe", "Te", "Latte", "Marmellata"]},
    "Condimenti": {"icon": "shaker", "children": ["Olio", "Aceto", "Spezie", "Salse"]},
    "Conserve": {"icon": "food-variant", "children": ["Pomodoro", "Legumi", "Tonno", "Verdure"]},
    "Dolci": {"icon": "cake-variant", "children": ["Cioccolato", "Caramelle", "Torte"]},
    "Formaggi": {"icon": "cheese", "children": ["Freschi", "Stagionati", "Grattugiati"]},
    "Frutta": {"icon": "fruit-watermelon", "children": ["Fresca", "Secca", "Disidratata"]},
    "Gastronomia": {"icon": "food-turkey", "children": ["Piatti pronti", "Insalate"]},
    "Igiene": {"icon": "hand-wash", "children": ["Corpo", "Orale", "Capelli"]},
    "Latticini": {"icon": "cow", "children": ["Latte", "Yogurt", "Panna", "Burro"]},
    "Pane": {"icon": "bread-slice", "children": ["Fresco", "Confezionato", "Grissini"]},
    "Pasta": {"icon": "pasta", "children": ["Secca", "Fresca", "Ripiena", "Riso"]},
    "Pesce": {"icon": "fish", "children": ["Fresco", "Surgelato", "Conserve"]},
    "Pulizia": {"icon": "spray-bottle", "children": ["Casa", "Bucato", "Piatti"]},
    "Salumi": {"icon": "food-drumstick", "children": ["Prosciutto", "Salame", "Wurstel"]},
    "Snack": {"icon": "food-croissant", "children": ["Patatine", "Barrette", "Salatini"]},
    "Surgelati": {"icon": "snowflake", "children": ["Verdure", "Pizza", "Gelati", "Pesce"]},
    "Verdura": {"icon": "leaf", "children": ["Fresca", "IV gamma", "Conservata"]},
}


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=True),
        sa.Column("icon", sa.String(100), nullable=True),
        sa.Column("sort_order", sa.Integer, default=0),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])
    op.create_index("ix_categories_slug", "categories", ["slug"], unique=True)

    # Seed category tree
    conn = op.get_bind()
    sort_idx = 0
    for parent_name, info in CATEGORY_TREE.items():
        parent_id = uuid.uuid4()
        parent_slug = parent_name.lower().replace(" ", "-")
        conn.execute(
            sa.text(
                "INSERT INTO categories (id, name, slug, parent_id, icon, sort_order) "
                "VALUES (:id, :name, :slug, NULL, :icon, :sort_order)"
            ),
            {"id": str(parent_id), "name": parent_name, "slug": parent_slug, "icon": info["icon"], "sort_order": sort_idx},
        )
        sort_idx += 1
        for child_idx, child_name in enumerate(info.get("children", [])):
            child_slug = f"{parent_slug}/{child_name.lower().replace(' ', '-')}"
            conn.execute(
                sa.text(
                    "INSERT INTO categories (id, name, slug, parent_id, icon, sort_order) "
                    "VALUES (:id, :name, :slug, :parent_id, NULL, :sort_order)"
                ),
                {"id": str(uuid.uuid4()), "name": child_name, "slug": child_slug, "parent_id": str(parent_id), "sort_order": child_idx},
            )


def downgrade() -> None:
    op.drop_table("categories")
