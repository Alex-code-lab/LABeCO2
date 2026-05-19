# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests du détail affiché dans la fenêtre de validation."""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ui.validation_details import format_entry_detail


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE sources (
            id TEXT PRIMARY KEY,
            title TEXT
        );
        CREATE TABLE contributors (
            id TEXT PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE emission_factors (
            id TEXT PRIMARY KEY,
            name TEXT,
            co2_factor REAL
        );
        CREATE TABLE materials (
            id TEXT PRIMARY KEY,
            name TEXT,
            emission_factor_id TEXT
        );
        CREATE TABLE commercial_products (
            id TEXT PRIMARY KEY,
            name TEXT,
            code_nacres TEXT,
            product_type TEXT,
            price_sold_packaging REAL,
            units_per_sold_packaging INTEGER,
            sold_unit_volume_ml REAL,
            capacity_volume_ml REAL,
            emission_factor_id TEXT,
            source_id TEXT,
            contributor_id TEXT,
            status TEXT,
            note TEXT
        );
        CREATE TABLE product_components (
            id TEXT PRIMARY KEY,
            product_id TEXT,
            component_type TEXT,
            material_id TEXT,
            mass_g REAL,
            units_divisor INTEGER
        );
    """)
    return conn


def test_product_detail_lists_solid_components():
    conn = _make_db()
    conn.execute("INSERT INTO emission_factors(id, name, co2_factor) VALUES('ef1', 'PP', 3.1)")
    conn.execute("INSERT INTO materials(id, name, emission_factor_id) VALUES('m1', 'Polypropylène (PP)', 'ef1')")
    conn.execute("""
        INSERT INTO commercial_products(
            id, name, code_nacres, product_type, price_sold_packaging,
            units_per_sold_packaging, status
        ) VALUES('p1', 'Tube test', 'NB11', 'solid', 42, 100, 'draft')
    """)
    conn.execute("""
        INSERT INTO product_components(
            id, product_id, component_type, material_id, mass_g, units_divisor
        ) VALUES('pc1', 'p1', 'product', 'm1', 6.7, 1)
    """)

    detail = format_entry_detail(conn, "commercial_products", "p1")

    assert "Composants détaillés : 1" in detail
    assert "Polypropylène (PP)" in detail
    assert "6.7 g" in detail


def test_product_detail_flags_liquid_factor_to_link():
    conn = _make_db()
    conn.execute("""
        INSERT INTO commercial_products(
            id, name, code_nacres, product_type, sold_unit_volume_ml, status
        ) VALUES('p2', 'Vinaigre test', 'BB02', 'liquid', 1500, 'draft')
    """)

    detail = format_entry_detail(conn, "commercial_products", "p2")

    assert "Facteur liquide : À relier" in detail
    assert "1500.0 mL" in detail


def test_product_detail_shows_note():
    conn = _make_db()
    conn.execute("""
        INSERT INTO commercial_products(
            id, name, code_nacres, product_type, status, note
        ) VALUES(
            'p-note', 'Ampicillin Sodium salt 1g', 'NA76', 'solid', 'draft',
            'https://example.org/ampicillin ; remarque validation'
        )
    """)

    detail = format_entry_detail(conn, "commercial_products", "p-note")

    assert (
        "Lien / Note / Remarque : https://example.org/ampicillin ; remarque validation"
        in detail
    )


def test_product_detail_ignores_blank_mass_product_components():
    conn = _make_db()
    conn.execute("INSERT INTO emission_factors(id, name, co2_factor) VALUES('ef1', 'PS', 3.5)")
    conn.execute("INSERT INTO materials(id, name, emission_factor_id) VALUES('m1', 'Polystyrène (PS)', 'ef1')")
    conn.execute("""
        INSERT INTO commercial_products(id, name, code_nacres, product_type, status)
        VALUES('p3', 'Flask test', 'NB13', 'solid', 'validated')
    """)
    conn.execute("""
        INSERT INTO product_components(
            id, product_id, component_type, material_id, mass_g, units_divisor
        ) VALUES('pc1', 'p3', 'product', 'm1', 20.9, 1)
    """)
    conn.execute("""
        INSERT INTO product_components(
            id, product_id, component_type, material_id, mass_g, units_divisor
        ) VALUES('pc2', 'p3', 'product', 'm1', NULL, 1)
    """)

    detail = format_entry_detail(conn, "commercial_products", "p3")

    assert "Composants détaillés : 1" in detail
    assert "20.9 g" in detail
    assert "masse manquante" not in detail


def test_product_detail_keeps_incomplete_packaging_divisor_context():
    conn = _make_db()
    conn.execute("INSERT INTO emission_factors(id, name, co2_factor) VALUES('ef1', 'Papier', 1.05)")
    conn.execute("INSERT INTO materials(id, name, emission_factor_id) VALUES('m1', 'Papier', 'ef1')")
    conn.execute("""
        INSERT INTO commercial_products(id, name, code_nacres, product_type, status)
        VALUES('p4', 'Pain du voisin', 'AA01', 'solid', 'validated')
    """)
    conn.execute("""
        INSERT INTO product_components(
            id, product_id, component_type, material_id, mass_g, units_divisor
        ) VALUES('pc1', 'p4', 'primary_packaging', 'm1', NULL, 50)
    """)

    detail = format_entry_detail(conn, "commercial_products", "p4")

    assert "Composants détaillés : 0" in detail
    assert "Données composant à compléter : 1" in detail
    assert "primary_packaging : Papier ; masse manquante ; diviseur 50" in detail


def test_product_detail_shows_revision_diff():
    conn = _make_db()
    conn.execute("ALTER TABLE commercial_products ADD COLUMN revision_of_id TEXT")
    conn.execute("""
        INSERT INTO commercial_products(
            id, name, code_nacres, product_type, price_sold_packaging, status
        ) VALUES('old-p', 'Tube test', 'NB11', 'solid', 40, 'deprecated')
    """)
    conn.execute("""
        INSERT INTO commercial_products(
            id, name, code_nacres, product_type, price_sold_packaging, status,
            revision_of_id, note
        ) VALUES(
            'new-p', 'Tube test', 'NB11', 'solid', 55, 'draft', 'old-p',
            'https://example.org/tube'
        )
    """)

    detail = format_entry_detail(conn, "commercial_products", "new-p")

    assert "Nature : Modification" in detail
    assert "Modification de : Tube test (old-p)" in detail
    assert "Prix conditionnement : 40.0 -> 55.0" in detail
    assert "Lien / Note / Remarque : (vide) -> https://example.org/tube" in detail
    assert detail.index("Composants détaillés : 0") < detail.index("Changements :")
