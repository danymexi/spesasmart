"""Add 7 new supermarket chains and target stores.

Adds Carrefour, Conad, Eurospin, Aldi, MD Discount, Penny Market,
and PAM Panorama with stores in the Monza e Brianza area.

Revision ID: 022
Revises: 021
"""

from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Insert 7 new chains
    op.execute("""
        INSERT INTO chains (name, slug, website_url) VALUES
            ('Carrefour', 'carrefour', 'https://www.carrefour.it'),
            ('Conad', 'conad', 'https://www.conad.it'),
            ('Eurospin', 'eurospin', 'https://www.eurospin.it'),
            ('Aldi', 'aldi', 'https://www.aldi.it'),
            ('MD Discount', 'md-discount', 'https://www.mdspa.it'),
            ('Penny Market', 'penny', 'https://www.penny.it'),
            ('PAM Panorama', 'pam', 'https://www.pampanorama.it')
        ON CONFLICT (slug) DO NOTHING
    """)

    # Insert target stores (Monza e Brianza area)
    op.execute("""
        INSERT INTO stores (chain_id, name, address, city, province, zip_code) VALUES
            -- Carrefour
            ((SELECT id FROM chains WHERE slug = 'carrefour'),
             'Carrefour Monza', 'Via Lecco 2', 'Monza', 'MB', '20900'),
            ((SELECT id FROM chains WHERE slug = 'carrefour'),
             'Carrefour Lissone', 'Via Matteotti 65', 'Lissone', 'MB', '20851'),
            -- Conad
            ((SELECT id FROM chains WHERE slug = 'conad'),
             'Conad Monza', 'Via Borgazzi 65', 'Monza', 'MB', '20900'),
            ((SELECT id FROM chains WHERE slug = 'conad'),
             'Conad Desio', 'Via Milano 80', 'Desio', 'MB', '20832'),
            -- Eurospin
            ((SELECT id FROM chains WHERE slug = 'eurospin'),
             'Eurospin Biassono', 'Via Milano 20', 'Biassono', 'MB', '20853'),
            ((SELECT id FROM chains WHERE slug = 'eurospin'),
             'Eurospin Lissone', 'Via Bottego 5', 'Lissone', 'MB', '20851'),
            -- Aldi
            ((SELECT id FROM chains WHERE slug = 'aldi'),
             'Aldi Monza', 'Viale Lombardia 50', 'Monza', 'MB', '20900'),
            -- MD Discount
            ((SELECT id FROM chains WHERE slug = 'md-discount'),
             'MD Discount Monza', 'Via Borgazzi 90', 'Monza', 'MB', '20900'),
            ((SELECT id FROM chains WHERE slug = 'md-discount'),
             'MD Desio', 'Via Gramsci 15', 'Desio', 'MB', '20832'),
            -- Penny Market
            ((SELECT id FROM chains WHERE slug = 'penny'),
             'Penny Market Monza', 'Via Lecco 60', 'Monza', 'MB', '20900'),
            ((SELECT id FROM chains WHERE slug = 'penny'),
             'Penny Lissone', 'Via San Carlo 10', 'Lissone', 'MB', '20851'),
            -- PAM Panorama
            ((SELECT id FROM chains WHERE slug = 'pam'),
             'PAM Monza', 'Via Libertà 30', 'Monza', 'MB', '20900')
    """)


def downgrade() -> None:
    # Remove stores for the new chains
    op.execute("""
        DELETE FROM stores WHERE chain_id IN (
            SELECT id FROM chains WHERE slug IN (
                'carrefour', 'conad', 'eurospin', 'aldi',
                'md-discount', 'penny', 'pam'
            )
        )
    """)
    # Remove chains
    op.execute("""
        DELETE FROM chains WHERE slug IN (
            'carrefour', 'conad', 'eurospin', 'aldi',
            'md-discount', 'penny', 'pam'
        )
    """)
