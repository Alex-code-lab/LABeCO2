# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests d'import catalogue fournisseur dans lab_admin."""

import csv
import sqlite3

from tools.admin.catalogue_import import apply_catalogue_import, preview_catalogue_import
from ui.sqlite_schema import ensure_app_schema


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
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
            capacity_volume_ml REAL,
            emission_factor_id TEXT,
            ijm_catalogue_id TEXT,
            source_id TEXT,
            contributor_id TEXT,
            created_at TEXT,
            updated_at TEXT,
            status TEXT,
            contribution_id TEXT,
            revision_of_id TEXT,
            validated_by_id TEXT,
            validated_at TEXT,
            deprecated_at TEXT
        );
        """
    )
    ensure_app_schema(conn)
    return conn


def _write_catalogue(path):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "fournisseur",
                "catalogue_date",
                "code_fournisseur",
                "designation",
                "marque",
                "condt",
                "prix_ht",
                "nb_unites",
                "code_nacres",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "fournisseur": "DUCHEFA",
            "catalogue_date": "2026",
            "code_fournisseur": "A0001.0100",
            "designation": "Agar test",
            "marque": "Duchefa",
            "condt": "100 g",
            "prix_ht": "12.5",
            "nb_unites": "1",
            "code_nacres": "NA25",
        })


def test_catalogue_preview_and_apply_create_pending_idempotently(tmp_path):
    csv_path = tmp_path / "catalogue.csv"
    _write_catalogue(csv_path)
    conn = _make_db()

    preview = preview_catalogue_import(conn, csv_path)
    assert preview.summary["new_products"] == 1

    stats = apply_catalogue_import(conn, preview)
    conn.commit()

    assert stats["created_pending"] == 1
    assert conn.execute("SELECT COUNT(*) FROM supplier_catalogue").fetchone()[0] == 1
    assert conn.execute("SELECT status FROM commercial_products").fetchone()[0] == "pending"

    preview_2 = preview_catalogue_import(conn, csv_path)
    stats_2 = apply_catalogue_import(conn, preview_2)
    conn.commit()

    assert stats_2["created_pending"] == 0
    assert conn.execute("SELECT COUNT(*) FROM supplier_catalogue").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM commercial_products").fetchone()[0] == 1


def test_catalogue_preview_links_existing_without_overwriting(tmp_path):
    csv_path = tmp_path / "catalogue.csv"
    _write_catalogue(csv_path)
    conn = _make_db()
    conn.execute(
        """
        INSERT INTO commercial_products(
            id, name, brand, reference, code_nacres, product_type,
            sold_packaging_label, price_sold_packaging, status
        ) VALUES('existing','Old name','Duchefa','A0001.0100','NA25','solid','50 g',1.0,'validated')
        """
    )

    preview = preview_catalogue_import(conn, csv_path)
    assert preview.summary["linked_existing"] == 1
    assert preview.summary["price_changed"] == 1
    assert preview.summary["packaging_changed"] == 1

    stats = apply_catalogue_import(conn, preview)
    conn.commit()

    assert stats["created_pending"] == 0
    row = conn.execute(
        "SELECT name, price_sold_packaging, supplier_catalogue_id FROM commercial_products WHERE id='existing'"
    ).fetchone()
    assert row[0] == "Old name"
    assert row[1] == 1.0
    assert row[2]

