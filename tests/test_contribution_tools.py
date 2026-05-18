# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests des outils export/import de contribution JSON."""

import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_REFERENCE_DB = ROOT / "data" / "labeco2_reference.sqlite"

from tools.export_contribution import (
    collect_dependencies,
    collect_product_components,
    export_table,
    fetch_all,
)
from tools.import_contribution import (
    diff_rows,
    import_dependencies,
    upsert_row,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _migrated_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "labeco2.sqlite"
    shutil.copy(_REFERENCE_DB, db_path)
    return db_path


def _open(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Tests export_contribution (fonctions utilitaires)
# ---------------------------------------------------------------------------

def test_export_table_draft_only(tmp_path):
    db_path = _migrated_db(tmp_path)
    with _open(db_path) as conn:
        # Insérer un draft et un validated
        conn.execute(
            "INSERT INTO emission_factors(id, name, name_key, factor_type, status)"
            " VALUES('ef-test-1','Test draft','test draft','solid','draft')"
        )
        conn.execute(
            "INSERT INTO emission_factors(id, name, name_key, factor_type, status)"
            " VALUES('ef-test-2','Test validated','test validated','solid','validated')"
        )
        conn.commit()
        rows = export_table(conn, "emission_factors", "", [], "= 'draft'")

    ids = [r["id"] for r in rows]
    assert "ef-test-1" in ids
    assert "ef-test-2" not in ids


def test_export_table_all_statuses(tmp_path):
    db_path = _migrated_db(tmp_path)
    with _open(db_path) as conn:
        conn.execute(
            "INSERT INTO emission_factors(id, name, name_key, factor_type, status)"
            " VALUES('ef-test-3','Test all','test all','solid','validated')"
        )
        conn.commit()
        rows = export_table(
            conn, "emission_factors", "", [], "IN ('draft', 'validated')"
        )

    ids = [r["id"] for r in rows]
    assert "ef-test-3" in ids


def test_collect_dependencies_finds_source_and_contributor(tmp_path):
    db_path = _migrated_db(tmp_path)
    with _open(db_path) as conn:
        src_id = "src-test-dep"
        contrib_id = "contrib-test-dep"
        conn.execute(
            "INSERT INTO contributors(id, name, created_at, updated_at)"
            " VALUES(?,?,?,?)",
            (contrib_id, "Contrib Test", "2026-01-01", "2026-01-01"),
        )
        conn.execute(
            "INSERT INTO sources(id, title, contributor_id, status, created_at, updated_at)"
            " VALUES(?,?,?,?,?,?)",
            (src_id, "Source Test", contrib_id, "validated", "2026-01-01", "2026-01-01"),
        )
        conn.commit()

        entries = [
            {"table": "emission_factors", "id": "x", "data": {
                "source_id": src_id, "contributor_id": contrib_id
            }}
        ]
        sources, contributors = collect_dependencies(conn, entries)

    assert any(s["id"] == src_id for s in sources)
    assert any(c["id"] == contrib_id for c in contributors)


def test_collect_product_components_returns_linked_rows(tmp_path):
    db_path = _migrated_db(tmp_path)
    with _open(db_path) as conn:
        product_ids = conn.execute(
            "SELECT DISTINCT product_id FROM product_components LIMIT 3"
        ).fetchall()

    if not product_ids:
        return  # pas de composants dans cette base, test non applicable

    with _open(db_path) as conn:
        ids = [r[0] for r in product_ids]
        comps = collect_product_components(conn, ids)

    assert len(comps) > 0
    assert all(c["product_id"] in ids for c in comps)


# ---------------------------------------------------------------------------
# Tests import_contribution (fonctions utilitaires)
# ---------------------------------------------------------------------------

def test_diff_rows_detects_changed_value():
    old = {"name": "A", "status": "draft", "co2_factor": 1.0}
    new = {"name": "A", "status": "draft", "co2_factor": 2.0}
    diffs = diff_rows(old, new)
    assert any("co2_factor" in d for d in diffs)


def test_diff_rows_skips_ignored_cols():
    old = {"name": "A", "name_key": "a", "updated_at": "2026-01-01"}
    new = {"name": "A", "name_key": "b", "updated_at": "2026-06-01"}
    diffs = diff_rows(old, new)
    assert diffs == []


def test_diff_rows_no_change_returns_empty():
    row = {"name": "A", "co2_factor": 1.0, "status": "draft"}
    assert diff_rows(row, row) == []


def test_upsert_row_new_inserts(tmp_path):
    db_path = _migrated_db(tmp_path)
    conn = sqlite3.connect(db_path)
    data = {
        "id": "ef-import-test",
        "name": "Facteur importé",
        "name_key": "facteur importe",
        "factor_type": "solid",
        "status": "draft",
        "created_at": "2026-01-01",
        "updated_at": "2026-01-01",
    }
    result = upsert_row(conn, "emission_factors", data, validate=False, dry_run=False)
    conn.commit()
    assert result == "new"
    row = conn.execute(
        "SELECT name FROM emission_factors WHERE id='ef-import-test'"
    ).fetchone()
    assert row is not None
    assert row[0] == "Facteur importé"
    conn.close()


def test_upsert_row_skips_identical(tmp_path):
    db_path = _migrated_db(tmp_path)
    conn = sqlite3.connect(db_path)
    data = {
        "id": "ef-skip-test",
        "name": "Facteur skip",
        "name_key": "facteur skip",
        "factor_type": "solid",
        "status": "draft",
        "created_at": "2026-01-01",
        "updated_at": "2026-01-01",
    }
    upsert_row(conn, "emission_factors", data, validate=False, dry_run=False)
    conn.commit()
    result = upsert_row(conn, "emission_factors", data, validate=False, dry_run=False)
    assert result == "skipped"
    conn.close()


def test_upsert_row_updates_changed_value(tmp_path):
    db_path = _migrated_db(tmp_path)
    conn = sqlite3.connect(db_path)
    data = {
        "id": "ef-update-test",
        "name": "Facteur update",
        "name_key": "facteur update",
        "factor_type": "solid",
        "co2_factor": 1.0,
        "status": "draft",
        "created_at": "2026-01-01",
        "updated_at": "2026-01-01",
    }
    upsert_row(conn, "emission_factors", data, validate=False, dry_run=False)
    conn.commit()
    data2 = dict(data, co2_factor=9.9)
    result = upsert_row(conn, "emission_factors", data2, validate=False, dry_run=False)
    conn.commit()
    assert result == "updated"
    val = conn.execute(
        "SELECT co2_factor FROM emission_factors WHERE id='ef-update-test'"
    ).fetchone()[0]
    assert val == 9.9
    conn.close()


def test_upsert_row_dry_run_does_not_insert(tmp_path):
    db_path = _migrated_db(tmp_path)
    conn = sqlite3.connect(db_path)
    data = {
        "id": "ef-dryrun-test",
        "name": "Ne doit pas exister",
        "status": "draft",
        "created_at": "2026-01-01",
        "updated_at": "2026-01-01",
    }
    upsert_row(conn, "emission_factors", data, validate=False, dry_run=True)
    row = conn.execute(
        "SELECT id FROM emission_factors WHERE id='ef-dryrun-test'"
    ).fetchone()
    assert row is None
    conn.close()


def test_upsert_row_product_component_without_updated_at_column(tmp_path):
    db_path = _migrated_db(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO emission_factors(id, name, name_key, factor_type, status)"
        " VALUES('ef-component-test','Facteur composant','facteur composant','solid','draft')"
    )
    conn.execute(
        "INSERT INTO materials(id, name, name_key, emission_factor_id, status)"
        " VALUES('mat-component-test','Matière composant','matiere composant','ef-component-test','draft')"
    )
    conn.execute(
        "INSERT INTO commercial_products(id, name, code_nacres, product_type, status)"
        " VALUES('prod-component-test','Produit composant','AA01','solid','draft')"
    )
    data = {
        "id": "pc-component-test",
        "product_id": "prod-component-test",
        "component_type": "product",
        "material_id": "mat-component-test",
        "mass_g": 12.5,
        "units_divisor": 1,
    }
    result = upsert_row(conn, "product_components", data, validate=False, dry_run=False)
    conn.commit()
    assert result == "new"
    row = conn.execute(
        "SELECT mass_g FROM product_components WHERE id='pc-component-test'"
    ).fetchone()
    assert row is not None
    assert row[0] == 12.5
    conn.close()


def test_import_dependencies_inserts_missing_contributor(tmp_path):
    db_path = _migrated_db(tmp_path)
    conn = sqlite3.connect(db_path)
    payload = {
        "contributors": [
            {"id": "contrib-new-1", "name": "Nouveau Contrib",
             "created_at": "2026-01-01", "updated_at": "2026-01-01"}
        ],
        "sources": [],
    }
    import_dependencies(conn, payload, dry_run=False)
    conn.commit()
    row = conn.execute(
        "SELECT name FROM contributors WHERE id='contrib-new-1'"
    ).fetchone()
    assert row is not None
    assert row[0] == "Nouveau Contrib"
    conn.close()


def test_import_dependencies_skips_existing_contributor(tmp_path):
    db_path = _migrated_db(tmp_path)
    conn = sqlite3.connect(db_path)
    existing = conn.execute(
        "SELECT id, name FROM contributors LIMIT 1"
    ).fetchone()
    original_name = existing[1]
    payload = {
        "contributors": [
            {"id": existing[0], "name": "Nom modifié",
             "created_at": "2026-01-01", "updated_at": "2026-01-01"}
        ],
        "sources": [],
    }
    import_dependencies(conn, payload, dry_run=False)
    conn.commit()
    row = conn.execute(
        "SELECT name FROM contributors WHERE id=?", (existing[0],)
    ).fetchone()
    assert row[0] == original_name  # pas écrasé
    conn.close()


# ---------------------------------------------------------------------------
# Test de round-trip export → import
# ---------------------------------------------------------------------------

def test_roundtrip_export_import(tmp_path):
    """Export des emission_factors d'une base, import dans une base vide."""
    src_db = _migrated_db(tmp_path)
    dst_db = tmp_path / "dst.sqlite"
    shutil.copy(_REFERENCE_DB, dst_db)

    with _open(src_db) as conn:
        rows = export_table(conn, "emission_factors", "", [], "IN ('draft', 'validated')")
        entries = [{"table": "emission_factors", "id": r["id"], "data": r} for r in rows]
        sources, contributors = collect_dependencies(conn, entries)

    payload = {
        "format_version": "1",
        "exported_at": "2026-05-18T00:00:00+00:00",
        "contributor": None,
        "sources": sources,
        "contributors": contributors,
        "entries": entries,
    }
    json_path = tmp_path / "contrib.json"
    json_path.write_text(json.dumps(payload, default=str), encoding="utf-8")

    dst_conn = sqlite3.connect(dst_db)
    import_dependencies(dst_conn, payload, dry_run=False)
    stats = {"new": 0, "updated": 0, "skipped": 0}
    for entry in entries:
        result = upsert_row(
            dst_conn, entry["table"], entry["data"], validate=False, dry_run=False
        )
        stats[result] += 1
    dst_conn.commit()

    src_count = sqlite3.connect(src_db).execute(
        "SELECT COUNT(*) FROM emission_factors"
    ).fetchone()[0]
    dst_count = dst_conn.execute(
        "SELECT COUNT(*) FROM emission_factors"
    ).fetchone()[0]
    dst_conn.close()

    assert dst_count == src_count
    assert stats["new"] + stats["skipped"] + stats["updated"] == len(entries)
