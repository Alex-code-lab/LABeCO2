# SPDX-License-Identifier: GPL-3.0-or-later
"""Évolutions légères du schéma SQLite applicatif."""

from __future__ import annotations

import sqlite3


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


_CREATE_SUPPLIER_CATALOGUE = """
CREATE TABLE IF NOT EXISTS supplier_catalogue (
    id                TEXT PRIMARY KEY,
    supplier          TEXT NOT NULL,
    catalogue_date    TEXT,
    code_fournisseur  TEXT,
    designation       TEXT,
    brand             TEXT,
    conditionnement   TEXT,
    price_ht          REAL,
    units_per_pack    INTEGER,
    mass_g            REAL,
    volume_ml         REAL,
    imported_at       TEXT
)
"""

_CREATE_ADMIN_IMPORT_BATCHES = """
CREATE TABLE IF NOT EXISTS admin_import_batches (
    id            TEXT PRIMARY KEY,
    import_type   TEXT NOT NULL,
    file_path     TEXT,
    supplier      TEXT,
    catalogue_date TEXT,
    created_at    TEXT NOT NULL,
    summary_json  TEXT,
    status        TEXT NOT NULL DEFAULT 'preview'
)
"""

_CREATE_ADMIN_MERGE_DECISIONS = """
CREATE TABLE IF NOT EXISTS admin_merge_decisions (
    id          TEXT PRIMARY KEY,
    batch_id    TEXT,
    table_name  TEXT NOT NULL,
    row_id      TEXT,
    decision    TEXT NOT NULL,
    validator   TEXT,
    note        TEXT,
    created_at  TEXT NOT NULL
)
"""

_CREATE_SUPPLIER_GENERIC_PRODUCTS = """
CREATE TABLE IF NOT EXISTS supplier_generic_products (
    id                  TEXT PRIMARY KEY,
    product_name_short  TEXT,
    generic_category    TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE(product_name_short, generic_category)
)
"""

_CREATE_SUPPLIER_REFERENCES = """
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
)
"""

_CREATE_SUPPLIER_PRICE_CACHE = """
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
)
"""

_CREATE_SUPPLIER_SCRAPE_RUNS = """
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
)
"""

_CREATE_SUPPLIER_FETCH_LOG = """
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
)
"""


def ensure_app_schema(conn: sqlite3.Connection) -> None:
    """Ajoute les colonnes applicatives manquantes sur les bases existantes."""
    conn.execute(_CREATE_SUPPLIER_CATALOGUE)
    conn.execute(_CREATE_ADMIN_IMPORT_BATCHES)
    conn.execute(_CREATE_ADMIN_MERGE_DECISIONS)
    conn.execute(_CREATE_SUPPLIER_GENERIC_PRODUCTS)
    conn.execute(_CREATE_SUPPLIER_REFERENCES)
    conn.execute(_CREATE_SUPPLIER_PRICE_CACHE)
    conn.execute(_CREATE_SUPPLIER_SCRAPE_RUNS)
    conn.execute(_CREATE_SUPPLIER_FETCH_LOG)
    # Une même page fournisseur peut exposer plusieurs variantes/références.
    # L'unicité métier reste donc supplier + supplier_product_ref, pas l'URL.
    conn.execute("DROP INDEX IF EXISTS idx_supplier_references_url")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_supplier_references_url
        ON supplier_references(supplier, product_url)
        WHERE product_url IS NOT NULL AND product_url != ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_supplier_references_generic_product
        ON supplier_references(generic_product_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_supplier_fetch_log_run
        ON supplier_fetch_log(run_id)
        """
    )

    nacres_columns = _columns(conn, "nacres_codes")
    if nacres_columns and "statut_maj_2026" not in nacres_columns:
        conn.execute("ALTER TABLE nacres_codes ADD COLUMN statut_maj_2026 TEXT")

    commercial_product_columns = _columns(conn, "commercial_products")
    if commercial_product_columns and "note" not in commercial_product_columns:
        conn.execute("ALTER TABLE commercial_products ADD COLUMN note TEXT")
    if commercial_product_columns and "supplier_catalogue_id" not in commercial_product_columns:
        conn.execute("ALTER TABLE commercial_products ADD COLUMN supplier_catalogue_id TEXT")

    supplier_catalogue_columns = _columns(conn, "supplier_catalogue")
    if supplier_catalogue_columns and "import_batch_id" not in supplier_catalogue_columns:
        conn.execute("ALTER TABLE supplier_catalogue ADD COLUMN import_batch_id TEXT")
    if supplier_catalogue_columns and "row_hash" not in supplier_catalogue_columns:
        conn.execute("ALTER TABLE supplier_catalogue ADD COLUMN row_hash TEXT")
    if supplier_catalogue_columns and "product_url" not in supplier_catalogue_columns:
        conn.execute("ALTER TABLE supplier_catalogue ADD COLUMN product_url TEXT")
    if supplier_catalogue_columns and "source_html_hash" not in supplier_catalogue_columns:
        conn.execute("ALTER TABLE supplier_catalogue ADD COLUMN source_html_hash TEXT")
    if supplier_catalogue_columns and "scraping_notes" not in supplier_catalogue_columns:
        conn.execute("ALTER TABLE supplier_catalogue ADD COLUMN scraping_notes TEXT")
    if supplier_catalogue_columns and "variant_attributes_json" not in supplier_catalogue_columns:
        conn.execute("ALTER TABLE supplier_catalogue ADD COLUMN variant_attributes_json TEXT")
    if supplier_catalogue_columns and "currency" not in supplier_catalogue_columns:
        conn.execute("ALTER TABLE supplier_catalogue ADD COLUMN currency TEXT")
