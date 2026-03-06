-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Supermercati (insegne)
CREATE TABLE chains (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        VARCHAR(50) UNIQUE NOT NULL,
    name        VARCHAR(100) NOT NULL,
    logo_url    TEXT,
    website_url TEXT,
    color_hex   VARCHAR(7),
    is_active   BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Punti vendita fisici
CREATE TABLE stores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chain_id        UUID REFERENCES chains(id),
    name            VARCHAR(200),
    address         TEXT,
    city            VARCHAR(100),
    postal_code     VARCHAR(10),
    province        CHAR(2),
    lat             DECIMAL(10, 8) NOT NULL,
    lng             DECIMAL(11, 8) NOT NULL,
    geom            GEOGRAPHY(POINT, 4326),
    phone           VARCHAR(20),
    hours           JSONB,
    is_online_only  BOOLEAN DEFAULT false,
    is_active       BOOLEAN DEFAULT true,
    last_verified   TIMESTAMPTZ
);

CREATE INDEX stores_geom_idx ON stores USING GIST(geom);
CREATE INDEX stores_chain_idx ON stores(chain_id);

-- Categorie prodotti (albero)
CREATE TABLE categories (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id   UUID REFERENCES categories(id),
    slug        VARCHAR(100) UNIQUE,
    name        VARCHAR(100) NOT NULL,
    icon        VARCHAR(50),
    sort_order  INT DEFAULT 0
);

-- Prodotto canonico (deduplicato, cross-store)
CREATE TABLE canonical_products (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(300) NOT NULL,
    brand               VARCHAR(150),
    category_id         UUID REFERENCES categories(id),
    quantity_value      DECIMAL(10, 3),
    quantity_unit       VARCHAR(20),
    quantity_raw        VARCHAR(100),
    barcode_ean         VARCHAR(20),
    image_url           TEXT,
    description         TEXT,
    tags                TEXT[],
    is_verified         BOOLEAN DEFAULT false,
    match_confidence    DECIMAL(4, 3),
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT name_not_empty CHECK (trim(name) != '')
);

CREATE INDEX canonical_products_ean_idx ON canonical_products(barcode_ean)
    WHERE barcode_ean IS NOT NULL;
CREATE INDEX canonical_products_name_trgm ON canonical_products
    USING GIN(name gin_trgm_ops);

-- Prodotto specifico di un negozio
CREATE TABLE store_products (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_product_id UUID REFERENCES canonical_products(id),
    store_id            UUID REFERENCES stores(id),
    chain_id            UUID REFERENCES chains(id),
    external_id         VARCHAR(200),
    name_original       VARCHAR(300),
    price               DECIMAL(8, 2) NOT NULL,
    price_discounted    DECIMAL(8, 2),
    discount_label      VARCHAR(100),
    discount_ends_at    DATE,
    price_per_unit      DECIMAL(10, 4),
    unit_label          VARCHAR(50),
    in_stock            BOOLEAN DEFAULT true,
    product_url         TEXT,
    last_scraped        TIMESTAMPTZ NOT NULL,
    scrape_hash         VARCHAR(64),
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX sp_canonical_idx ON store_products(canonical_product_id);
CREATE INDEX sp_chain_idx ON store_products(chain_id);
CREATE INDEX sp_last_scraped_idx ON store_products(last_scraped);
CREATE INDEX sp_canonical_chain_price ON store_products(canonical_product_id, chain_id, price)
    WHERE in_stock = true;

-- Utenti
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255),
    email_verified  BOOLEAN DEFAULT false,
    display_name    VARCHAR(100),
    avatar_url      TEXT,
    home_lat        DECIMAL(10, 8),
    home_lng        DECIMAL(11, 8),
    search_radius_km INT DEFAULT 20,
    preferred_chain_ids UUID[],
    excluded_chain_ids  UUID[],
    plan            VARCHAR(20) DEFAULT 'free',
    created_at      TIMESTAMPTZ DEFAULT now(),
    last_login      TIMESTAMPTZ
);

-- Refresh tokens
CREATE TABLE refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    token       VARCHAR(255) UNIQUE NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX refresh_tokens_user_idx ON refresh_tokens(user_id);

-- Liste della spesa
CREATE TABLE shopping_lists (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    name        VARCHAR(200) NOT NULL DEFAULT 'La mia lista',
    emoji       VARCHAR(10) DEFAULT '🛒',
    is_archived BOOLEAN DEFAULT false,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Elementi della lista
CREATE TABLE list_items (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    list_id                 UUID REFERENCES shopping_lists(id) ON DELETE CASCADE,
    canonical_product_id    UUID REFERENCES canonical_products(id),
    free_text_name          VARCHAR(300),
    quantity                DECIMAL(8, 3) NOT NULL DEFAULT 1,
    unit                    VARCHAR(20),
    is_checked              BOOLEAN DEFAULT false,
    note                    TEXT,
    sort_order              INT DEFAULT 0,
    added_at                TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX list_items_list_idx ON list_items(list_id);

-- Risultati comparazione (cache)
CREATE TABLE comparison_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    list_id         UUID REFERENCES shopping_lists(id) ON DELETE CASCADE,
    user_lat        DECIMAL(10, 8),
    user_lng        DECIMAL(11, 8),
    radius_km       INT,
    result_json     JSONB NOT NULL,
    computed_at     TIMESTAMPTZ DEFAULT now(),
    expires_at      TIMESTAMPTZ DEFAULT (now() + INTERVAL '6 hours')
);

-- Log scraping
CREATE TABLE scrape_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chain_id        UUID REFERENCES chains(id),
    started_at      TIMESTAMPTZ DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(20) DEFAULT 'running',
    products_scraped    INT DEFAULT 0,
    products_updated    INT DEFAULT 0,
    products_new        INT DEFAULT 0,
    error_message   TEXT,
    meta            JSONB
);

-- Coda matching manuale
CREATE TABLE match_review_queue (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_product_id    UUID REFERENCES store_products(id),
    suggested_canonical_id UUID REFERENCES canonical_products(id),
    match_score         DECIMAL(4, 3),
    match_reason        TEXT,
    reviewed_by         UUID REFERENCES users(id),
    review_action       VARCHAR(20),
    created_at          TIMESTAMPTZ DEFAULT now(),
    reviewed_at         TIMESTAMPTZ
);

-- Materialized View per prezzi minimi per prodotto
CREATE MATERIALIZED VIEW product_min_prices AS
SELECT
    canonical_product_id,
    MIN(COALESCE(price_discounted, price)) as min_price,
    COUNT(DISTINCT chain_id) as num_chains
FROM store_products
WHERE in_stock = true
    AND last_scraped > NOW() - INTERVAL '48 hours'
GROUP BY canonical_product_id;

-- Seed data: catene principali
INSERT INTO chains (slug, name, color_hex, website_url) VALUES
    ('esselunga', 'Esselunga', '#E30613', 'https://www.esselunga.it'),
    ('iperal', 'Iperal', '#003DA5', 'https://www.iperal.it'),
    ('conad', 'Conad', '#E2001A', 'https://www.conad.it'),
    ('coop', 'Coop', '#E2001A', 'https://www.e-coop.it'),
    ('carrefour', 'Carrefour', '#004E9A', 'https://www.carrefour.it'),
    ('penny', 'Penny Market', '#CD1719', 'https://www.penny.it');
