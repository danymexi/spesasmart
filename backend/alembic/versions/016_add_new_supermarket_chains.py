"""Add new Italian supermarket chains.

Inserts Conad, Carrefour, Eurospin, MD, Penny Market, Aldi, Bennet, Pam
into the chains table.

Revision ID: 016
Revises: 015
Create Date: 2026-03-07
"""
from typing import Sequence, Union

from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_CHAINS = [
    ("Conad", "conad", "https://www.conad.it"),
    ("Carrefour", "carrefour", "https://www.carrefour.it"),
    ("Eurospin", "eurospin", "https://www.eurospin.it"),
    ("MD", "md", "https://www.mdspa.it"),
    ("Penny Market", "penny", "https://www.pennymarket.it"),
    ("Aldi", "aldi", "https://www.aldi.it"),
    ("Bennet", "bennet", "https://www.bennet.com"),
    ("Pam", "pam", "https://www.pam.it"),
]


def upgrade() -> None:
    for name, slug, url in NEW_CHAINS:
        op.execute(
            f"INSERT INTO chains (id, name, slug, website_url) "
            f"VALUES (gen_random_uuid(), '{name}', '{slug}', '{url}') "
            f"ON CONFLICT (slug) DO NOTHING"
        )


def downgrade() -> None:
    slugs = ", ".join(f"'{slug}'" for _, slug, _ in NEW_CHAINS)
    op.execute(f"DELETE FROM chains WHERE slug IN ({slugs})")
