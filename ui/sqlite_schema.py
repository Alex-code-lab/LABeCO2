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


def ensure_app_schema(conn: sqlite3.Connection) -> None:
    """Ajoute les colonnes applicatives manquantes sur les bases existantes."""
    conn.execute(_CREATE_SUPPLIER_CATALOGUE)
    conn.execute(_CREATE_ADMIN_IMPORT_BATCHES)
    conn.execute(_CREATE_ADMIN_MERGE_DECISIONS)

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
