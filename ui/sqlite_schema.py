# SPDX-License-Identifier: GPL-3.0-or-later
"""Évolutions légères du schéma SQLite applicatif."""

from __future__ import annotations

import sqlite3


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def ensure_app_schema(conn: sqlite3.Connection) -> None:
    """Ajoute les colonnes applicatives manquantes sur les bases existantes."""
    commercial_product_columns = _columns(conn, "commercial_products")
    if commercial_product_columns and "note" not in commercial_product_columns:
        conn.execute("ALTER TABLE commercial_products ADD COLUMN note TEXT")
