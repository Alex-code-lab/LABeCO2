# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests des règles métier admin."""

import sqlite3

from tools.admin.workflow import check_entry_quality, promote_pending_products
from ui.sqlite_schema import ensure_app_schema


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE nacres_codes (
            id TEXT PRIMARY KEY,
            code TEXT,
            label TEXT,
            parent_code TEXT,
            statut_maj_2026 TEXT
        );
        CREATE TABLE purchase_factors (
            category TEXT,
            subcategory TEXT,
            subsubcategory TEXT
        );
        CREATE TABLE emission_factors (
            id TEXT PRIMARY KEY,
            name TEXT,
            source_id TEXT,
            co2_factor REAL,
            status TEXT
        );
        CREATE TABLE materials (
            id TEXT PRIMARY KEY,
            name TEXT,
            emission_factor_id TEXT,
            status TEXT
        );
        CREATE TABLE commercial_products (
            id TEXT PRIMARY KEY,
            name TEXT,
            brand TEXT,
            reference TEXT,
            code_nacres TEXT,
            product_type TEXT,
            sold_packaging_label TEXT,
            units_per_sold_packaging INTEGER,
            price_sold_packaging REAL,
            sold_unit_volume_ml REAL,
            emission_factor_id TEXT,
            status TEXT,
            updated_at TEXT
        );
        CREATE TABLE product_components (
            id TEXT PRIMARY KEY,
            product_id TEXT,
            component_type TEXT,
            material_id TEXT,
            mass_g REAL,
            units_divisor REAL
        );
        """
    )
    ensure_app_schema(conn)
    conn.execute(
        "INSERT INTO nacres_codes(id, code, label, parent_code, statut_maj_2026) VALUES('n1','NA25','Biochimie','NA','herite')"
    )
    conn.execute(
        "INSERT INTO nacres_codes(id, code, label, parent_code, statut_maj_2026) VALUES('n2','AA45','Nouveau','AA','nouveau')"
    )
    conn.execute(
        "INSERT INTO nacres_codes(id, code, label, parent_code, statut_maj_2026) VALUES('n3','ZZ99','Ancien','ZZ','a_ne_plus_utiliser')"
    )
    return conn


def test_product_quality_blocks_deprecated_nacres():
    conn = _make_db()
    row = {
        "id": "p1",
        "name": "Produit",
        "reference": "REF",
        "code_nacres": "ZZ99",
        "product_type": "solid",
        "sold_packaging_label": "10 g",
        "price_sold_packaging": 1.0,
        "status": "draft",
    }

    issues = check_entry_quality(conn, "commercial_products", row)

    assert "deprecated_nacres" in {issue.rule for issue in issues if issue.severity == "ERROR"}


def test_new_nacres_without_fe_is_warning_not_blocking():
    conn = _make_db()
    row = {
        "id": "p1",
        "name": "Produit",
        "reference": "REF",
        "code_nacres": "AA45",
        "product_type": "solid",
        "sold_packaging_label": "10 g",
        "price_sold_packaging": 1.0,
        "status": "pending",
    }

    issues = check_entry_quality(conn, "commercial_products", row)

    assert "new_nacres_without_fe" in {issue.rule for issue in issues if issue.severity == "WARNING"}
    assert not [issue for issue in issues if issue.severity == "ERROR"]


def test_promote_pending_products_promotes_only_complete_rows():
    conn = _make_db()
    conn.execute(
        """
        INSERT INTO commercial_products(
            id, name, reference, code_nacres, product_type,
            sold_packaging_label, price_sold_packaging, status
        ) VALUES('ok','Produit OK','REF1','NA25','solid','10 g',1.0,'pending')
        """
    )
    conn.execute(
        """
        INSERT INTO commercial_products(
            id, name, reference, code_nacres, product_type,
            sold_packaging_label, price_sold_packaging, status
        ) VALUES('bad','Produit KO','REF2','','solid','10 g',1.0,'pending')
        """
    )

    result = promote_pending_products(conn)
    conn.commit()

    assert result.promoted == ["ok"]
    assert "bad" in result.blocked
    assert conn.execute("SELECT status FROM commercial_products WHERE id='ok'").fetchone()[0] == "draft"
    assert conn.execute("SELECT status FROM commercial_products WHERE id='bad'").fetchone()[0] == "pending"

