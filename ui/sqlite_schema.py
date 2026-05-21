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


def ensure_app_schema(conn: sqlite3.Connection) -> None:
    """Ajoute les colonnes applicatives manquantes sur les bases existantes."""
    conn.execute(_CREATE_SUPPLIER_CATALOGUE)

    commercial_product_columns = _columns(conn, "commercial_products")
    if commercial_product_columns and "note" not in commercial_product_columns:
        conn.execute("ALTER TABLE commercial_products ADD COLUMN note TEXT")
    if commercial_product_columns and "supplier_catalogue_id" not in commercial_product_columns:
        conn.execute("ALTER TABLE commercial_products ADD COLUMN supplier_catalogue_id TEXT")
