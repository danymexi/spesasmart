-- SpesaSmart Database Schema

-- Catene di supermercati
CREATE TABLE IF NOT EXISTS chains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(50) UNIQUE NOT NULL,
    logo_url TEXT,
    website_url TEXT
);

-- Punti vendita
CREATE TABLE IF NOT EXISTS stores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chain_id UUID REFERENCES chains(id),
    name VARCHAR(200),
    address TEXT,
    city VARCHAR(100),
    province VARCHAR(10) DEFAULT 'MB',
    zip_code VARCHAR(10),
    lat DECIMAL(10, 7),
    lon DECIMAL(10, 7),
    phone VARCHAR(30),
    opening_hours JSONB,
    website_url TEXT,
    osm_id BIGINT UNIQUE
);

-- Volantini scaricati
CREATE TABLE IF NOT EXISTS flyers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chain_id UUID REFERENCES chains(id),
    store_id UUID REFERENCES stores(id),
    title VARCHAR(300),
    valid_from DATE NOT NULL,
    valid_to DATE NOT NULL,
    source_url TEXT,
    pages_count INTEGER,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pagine del volantino (immagini)
CREATE TABLE IF NOT EXISTS flyer_pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flyer_id UUID REFERENCES flyers(id),
    page_number INTEGER,
    image_url TEXT,
    ocr_raw_text TEXT,
    processed BOOLEAN DEFAULT FALSE
);

-- Catalogo prodotti (normalizzato)
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(300) NOT NULL,
    brand VARCHAR(200),
    category VARCHAR(100),
    subcategory VARCHAR(100),
    unit VARCHAR(50),
    barcode VARCHAR(50),
    image_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Prezzi/Offerte (cuore dell'app)
CREATE TABLE IF NOT EXISTS offers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID REFERENCES products(id),
    flyer_id UUID REFERENCES flyers(id),
    chain_id UUID REFERENCES chains(id),
    store_id UUID REFERENCES stores(id),
    original_price DECIMAL(8,2),
    offer_price DECIMAL(8,2) NOT NULL,
    discount_pct DECIMAL(5,2),
    discount_type VARCHAR(50),
    quantity VARCHAR(100),
    price_per_unit DECIMAL(8,2),
    valid_from DATE,
    valid_to DATE,
    raw_text TEXT,
    confidence DECIMAL(3,2),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indici per performance
CREATE INDEX IF NOT EXISTS idx_offers_product ON offers(product_id);
CREATE INDEX IF NOT EXISTS idx_offers_chain ON offers(chain_id);
CREATE INDEX IF NOT EXISTS idx_offers_dates ON offers(valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_offers_price ON offers(offer_price);
CREATE INDEX IF NOT EXISTS idx_products_name ON products USING gin(to_tsvector('italian', name));
CREATE INDEX IF NOT EXISTS idx_stores_lat_lon ON stores(lat, lon);

-- Tabella utenti
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_chat_id BIGINT,
    push_token TEXT,
    preferred_zone VARCHAR(100) DEFAULT 'Monza e Brianza',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Lista della spesa / prodotti seguiti
CREATE TABLE IF NOT EXISTS user_watchlist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(id),
    product_id UUID REFERENCES products(id),
    target_price DECIMAL(8,2),
    notify_any_offer BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, product_id)
);

-- Negozi preferiti dell'utente
CREATE TABLE IF NOT EXISTS user_stores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(id),
    store_id UUID REFERENCES stores(id),
    UNIQUE(user_id, store_id)
);

-- Dati iniziali: Catene
INSERT INTO chains (name, slug, website_url) VALUES
    ('Esselunga', 'esselunga', 'https://www.esselunga.it'),
    ('Lidl', 'lidl', 'https://www.lidl.it'),
    ('Coop', 'coop', 'https://www.e-coop.it'),
    ('Iperal', 'iperal', 'https://www.iperal.it'),
    ('Carrefour', 'carrefour', 'https://www.carrefour.it'),
    ('Conad', 'conad', 'https://www.conad.it'),
    ('Eurospin', 'eurospin', 'https://www.eurospin.it'),
    ('Aldi', 'aldi', 'https://www.aldi.it'),
    ('MD Discount', 'md-discount', 'https://www.mdspa.it'),
    ('Penny Market', 'penny', 'https://www.penny.it'),
    ('PAM Panorama', 'pam', 'https://www.pampanorama.it')
ON CONFLICT (slug) DO NOTHING;

-- Dati iniziali: Negozi Monza e Brianza
-- I primi 4 sono i negozi TARGET principali per lo scraping
INSERT INTO stores (chain_id, name, address, city, province, zip_code, lat, lon) VALUES
    -- TARGET: Esselunga Macherio
    ((SELECT id FROM chains WHERE slug = 'esselunga'), 'Esselunga Macherio', 'Via Milano 15', 'Macherio', 'MB', '20846', 45.6370, 9.2700),
    -- TARGET: Iperal Lesmo
    ((SELECT id FROM chains WHERE slug = 'iperal'), 'Iperal Lesmo', 'Via Nazionale dei Giovi', 'Lesmo', 'MB', '20855', 45.6480, 9.3060),
    -- TARGET: Lidl Biassono
    ((SELECT id FROM chains WHERE slug = 'lidl'), 'Lidl Biassono', 'Via Milano 40', 'Biassono', 'MB', '20853', 45.6320, 9.2820),
    -- TARGET: Coop Monza
    ((SELECT id FROM chains WHERE slug = 'coop'), 'Coop Monza', 'Via Italia 30', 'Monza', 'MB', '20900', 45.5840, 9.2740),
    -- Altri negozi zona
    ((SELECT id FROM chains WHERE slug = 'esselunga'), 'Esselunga Monza', 'Viale Elvezia 4', 'Monza', 'MB', '20900', 45.5810, 9.2710),
    ((SELECT id FROM chains WHERE slug = 'esselunga'), 'Esselunga Lissone', 'Via Matteotti 11', 'Lissone', 'MB', '20851', 45.6180, 9.2440),
    ((SELECT id FROM chains WHERE slug = 'esselunga'), 'Esselunga Desio', 'Via Milano 166', 'Desio', 'MB', '20832', 45.6130, 9.2100),
    ((SELECT id FROM chains WHERE slug = 'lidl'), 'Lidl Monza', 'Via Borgazzi 45', 'Monza', 'MB', '20900', 45.5780, 9.2800),
    ((SELECT id FROM chains WHERE slug = 'lidl'), 'Lidl Lissone', 'Via Carducci 50', 'Lissone', 'MB', '20851', 45.6150, 9.2480),
    ((SELECT id FROM chains WHERE slug = 'coop'), 'Coop Seregno', 'Via Stefano da Seregno 44', 'Seregno', 'MB', '20831', 45.6500, 9.2000),
    ((SELECT id FROM chains WHERE slug = 'iperal'), 'Iperal Seregno', 'Via Milano 5', 'Seregno', 'MB', '20831', 45.6520, 9.1980),
    ((SELECT id FROM chains WHERE slug = 'iperal'), 'Iperal Meda', 'Via Indipendenza 20', 'Meda', 'MB', '20821', 45.6610, 9.1530),
    -- Carrefour
    ((SELECT id FROM chains WHERE slug = 'carrefour'), 'Carrefour Monza', 'Via Lecco 2', 'Monza', 'MB', '20900', 45.5860, 9.2780),
    ((SELECT id FROM chains WHERE slug = 'carrefour'), 'Carrefour Lissone', 'Via Matteotti 65', 'Lissone', 'MB', '20851', 45.6160, 9.2460),
    -- Conad
    ((SELECT id FROM chains WHERE slug = 'conad'), 'Conad Monza', 'Via Borgazzi 65', 'Monza', 'MB', '20900', 45.5770, 9.2810),
    ((SELECT id FROM chains WHERE slug = 'conad'), 'Conad Desio', 'Via Milano 80', 'Desio', 'MB', '20832', 45.6100, 9.2130),
    -- Eurospin
    ((SELECT id FROM chains WHERE slug = 'eurospin'), 'Eurospin Biassono', 'Via Milano 20', 'Biassono', 'MB', '20853', 45.6340, 9.2790),
    ((SELECT id FROM chains WHERE slug = 'eurospin'), 'Eurospin Lissone', 'Via Bottego 5', 'Lissone', 'MB', '20851', 45.6140, 9.2420),
    -- Aldi
    ((SELECT id FROM chains WHERE slug = 'aldi'), 'Aldi Monza', 'Viale Lombardia 50', 'Monza', 'MB', '20900', 45.5900, 9.2680),
    -- MD Discount
    ((SELECT id FROM chains WHERE slug = 'md-discount'), 'MD Discount Monza', 'Via Borgazzi 90', 'Monza', 'MB', '20900', 45.5760, 9.2830),
    ((SELECT id FROM chains WHERE slug = 'md-discount'), 'MD Desio', 'Via Gramsci 15', 'Desio', 'MB', '20832', 45.6110, 9.2080),
    -- Penny Market
    ((SELECT id FROM chains WHERE slug = 'penny'), 'Penny Market Monza', 'Via Lecco 60', 'Monza', 'MB', '20900', 45.5870, 9.2760),
    ((SELECT id FROM chains WHERE slug = 'penny'), 'Penny Lissone', 'Via San Carlo 10', 'Lissone', 'MB', '20851', 45.6170, 9.2430),
    -- PAM Panorama
    ((SELECT id FROM chains WHERE slug = 'pam'), 'PAM Monza', 'Via Libertà 30', 'Monza', 'MB', '20900', 45.5830, 9.2720);
