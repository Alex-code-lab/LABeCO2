-- SPDX-License-Identifier: GPL-3.0-or-later
-- Tables intégrées LABeCO2 pour le scraper prudent de références fournisseurs.
-- La migration effective est également portée par ui.sqlite_schema.ensure_app_schema.

CREATE TABLE IF NOT EXISTS supplier_generic_products (
    id                  TEXT PRIMARY KEY,
    product_name_short  TEXT,
    generic_category    TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE(product_name_short, generic_category)
);

CREATE TABLE IF NOT EXISTS supplier_references (
    id                      TEXT PRIMARY KEY,
    generic_product_id      TEXT,
    supplier                TEXT NOT NULL,
    supplier_product_ref    TEXT NOT NULL,
    product_url             TEXT,
    product_name_short      TEXT,
    generic_category        TEXT,
    packaging_text          TEXT,
    price_publicly_visible  INTEGER NOT NULL DEFAULT 0,
    currency_detected       TEXT,
    retrieval_date          TEXT,
    source_html_hash        TEXT,
    scraping_notes          TEXT,
    first_seen_at           TEXT NOT NULL,
    last_seen_at            TEXT NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY(generic_product_id) REFERENCES supplier_generic_products(id),
    UNIQUE(supplier, supplier_product_ref)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_supplier_references_url
ON supplier_references(supplier, product_url)
WHERE product_url IS NOT NULL AND product_url != '';

CREATE TABLE IF NOT EXISTS supplier_price_cache (
    id                    TEXT PRIMARY KEY,
    supplier              TEXT NOT NULL,
    supplier_product_ref  TEXT NOT NULL,
    product_url           TEXT,
    price_value           REAL,
    currency              TEXT,
    retrieved_at          TEXT NOT NULL,
    source_html_hash      TEXT,
    retrieval_context     TEXT NOT NULL DEFAULT 'local_user',
    notes                 TEXT,
    UNIQUE(supplier, supplier_product_ref, retrieved_at)
);

CREATE TABLE IF NOT EXISTS supplier_scrape_runs (
    id                      TEXT PRIMARY KEY,
    supplier                TEXT,
    started_at              TEXT NOT NULL,
    finished_at             TEXT,
    status                  TEXT NOT NULL,
    dry_run                 INTEGER NOT NULL DEFAULT 1,
    config_path             TEXT,
    start_url_count         INTEGER NOT NULL DEFAULT 0,
    request_count           INTEGER NOT NULL DEFAULT 0,
    stored_reference_count  INTEGER NOT NULL DEFAULT 0,
    notes                   TEXT
);

CREATE TABLE IF NOT EXISTS supplier_fetch_log (
    id            TEXT PRIMARY KEY,
    run_id        TEXT,
    supplier      TEXT,
    url           TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,
    status_code   INTEGER,
    from_cache    INTEGER NOT NULL DEFAULT 0,
    html_hash     TEXT,
    error         TEXT,
    notes         TEXT,
    FOREIGN KEY(run_id) REFERENCES supplier_scrape_runs(id)
);

