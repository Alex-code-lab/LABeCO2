# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests des migrations légères du schéma SQLite."""

import sqlite3

from ui.sqlite_schema import ensure_app_schema
from ui.nacres_metadata import load_nacres_options


def test_ensure_app_schema_adds_nacres_2026_status_column():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE nacres_codes (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            label TEXT,
            parent_code TEXT
        )
        """
    )

    ensure_app_schema(conn)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(nacres_codes)")}
    assert "statut_maj_2026" in columns


def test_ensure_app_schema_adds_admin_audit_tables_and_catalogue_columns():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE commercial_products (
            id TEXT PRIMARY KEY,
            name TEXT,
            status TEXT
        )
        """
    )

    ensure_app_schema(conn)

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "admin_import_batches" in tables
    assert "admin_merge_decisions" in tables

    supplier_columns = {row[1] for row in conn.execute("PRAGMA table_info(supplier_catalogue)")}
    assert "import_batch_id" in supplier_columns
    assert "row_hash" in supplier_columns
    assert "product_url" in supplier_columns
    assert "source_html_hash" in supplier_columns
    assert "variant_attributes_json" in supplier_columns
    assert "currency" in supplier_columns


def test_load_nacres_options_flags_new_codes_without_purchase_factor():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE nacres_codes (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            label TEXT,
            parent_code TEXT,
            statut_maj_2026 TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE purchase_factors (
            category TEXT,
            subcategory TEXT,
            subsubcategory TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO nacres_codes(id, code, label, parent_code, statut_maj_2026) VALUES (?, ?, ?, ?, ?)",
        [
            ("1", "AA01", "Ancien avec FE", "AA", "herite"),
            ("2", "AA45", "Nouveau sans FE", "AA", "nouveau"),
            ("3", "AAT", "Hors nomenclature NACRES", None, None),
        ],
    )
    conn.execute(
        "INSERT INTO purchase_factors(category, subcategory, subsubcategory) VALUES (?, ?, ?)",
        ("Achats", "Consommables", "AA01 - Ancien avec FE"),
    )

    options = load_nacres_options(conn)

    assert [option.code for option in options] == ["AA01", "AA45"]
    by_code = {option.code: option for option in options}
    assert by_code["AA01"].has_purchase_factor
    assert not by_code["AA01"].is_new_without_labo1point5_fe
    assert not by_code["AA45"].has_purchase_factor
    assert by_code["AA45"].is_new_without_labo1point5_fe
