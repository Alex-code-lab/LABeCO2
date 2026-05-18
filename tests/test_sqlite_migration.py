# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests ciblés de la migration HDF5 vers SQLite."""

import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools.migrate_hdf5_to_sqlite import migrate_project_to_sqlite
from ui.data_manager import DataManager


ROOT_DIR = Path(__file__).resolve().parents[1]
REFERENCE_FIXTURE_DIR = ROOT_DIR / "tests" / "fixtures" / "migration_reference"


def _connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_migration_reference_fixtures_are_available():
    expected_files = {
        "catalogue_ijm.json",
        "liquid_factors.json",
        "material_factors.json",
        "purchase_factors.json",
        "solid_products.json",
        "transport_factors.json",
    }

    for filename in expected_files:
        path = REFERENCE_FIXTURE_DIR / filename
        assert path.exists(), filename
        rows = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(rows, list)
        assert rows, filename


def test_migration_creates_schema_and_core_tables(tmp_path):
    db_path = tmp_path / "labeco2.sqlite"
    report = migrate_project_to_sqlite(ROOT_DIR, db_path)

    assert db_path.exists()
    assert report.counts["purchase_factors"] > 1000
    assert report.counts["commercial_products"] > 900
    assert report.counts["liquid_emission_factors"] >= 30
    assert report.counts["materials"] >= 10
    assert report.counts["transport_factors"] >= 5

    with _connect(db_path) as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "schema_migrations",
            "contributors",
            "sources",
            "nacres_codes",
            "purchase_factors",
            "emission_factors",
            "materials",
            "commercial_products",
            "product_components",
            "catalogue_ijm",
            "transport_factors",
        }.issubset(tables)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migration_ignores_sqlite_runtime_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv(DataManager.SQLITE_ENV_VAR, str(tmp_path / "missing.sqlite"))

    db_path = tmp_path / "labeco2.sqlite"
    report = migrate_project_to_sqlite(ROOT_DIR, db_path)

    assert db_path.exists()
    assert report.counts["commercial_products"] > 900


def test_migration_keeps_capacity_objects_as_solid(tmp_path):
    db_path = tmp_path / "labeco2.sqlite"
    report = migrate_project_to_sqlite(ROOT_DIR, db_path)

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT product_type, sold_unit_volume_ml, capacity_volume_ml, emission_factor_id
            FROM commercial_products
            WHERE name LIKE 'BOITE à DÉCHETS 300ml%'
            LIMIT 1
            """
        ).fetchone()

    assert row is not None
    assert row["product_type"] == "solid"
    assert row["sold_unit_volume_ml"] is None
    assert row["capacity_volume_ml"] == 300.0
    assert row["emission_factor_id"] is None
    assert not any(
        item["name"].startswith("BOITE à DÉCHETS 300ml")
        for item in report.unresolved_liquid_products
    )


def test_migration_links_true_liquid_product_to_factor(tmp_path):
    db_path = tmp_path / "labeco2.sqlite"
    migrate_project_to_sqlite(ROOT_DIR, db_path)

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT product_type, sold_unit_volume_ml, capacity_volume_ml, emission_factor_id
            FROM commercial_products
            WHERE name = 'ACETONE NP 1 litre'
            LIMIT 1
            """
        ).fetchone()

    assert row is not None
    assert row["product_type"] == "liquid"
    assert row["sold_unit_volume_ml"] == 1000.0
    assert row["capacity_volume_ml"] is None
    assert row["emission_factor_id"]


def test_migration_reports_known_data_quality_issues(tmp_path):
    db_path = tmp_path / "labeco2.sqlite"
    report = migrate_project_to_sqlite(ROOT_DIR, db_path)

    assert report.negative_prices == []
    assert len(report.suspected_duplicates) >= 1
    assert len(report.unresolved_materials) >= 1
    assert len(report.unresolved_liquid_products) > 0
    assert len(report.unresolved_liquid_products) < 100
