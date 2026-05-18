# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests du mécanisme de révision : _prepare_revision + upsert sur entrée validée."""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.migrate_hdf5_to_sqlite import migrate_project_to_sqlite
from ui.sqlite_writer import _prepare_revision, upsert_liquid_factor, upsert_material_factor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_db() -> sqlite3.Connection:
    """Base en mémoire avec les colonnes minimales pour _prepare_revision."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE emission_factors (
            id TEXT PRIMARY KEY, name TEXT, name_key TEXT,
            status TEXT DEFAULT 'draft',
            deprecated_at TEXT, updated_at TEXT
        );
        CREATE TABLE commercial_products (
            id TEXT PRIMARY KEY, name TEXT,
            status TEXT DEFAULT 'draft',
            deprecated_at TEXT, updated_at TEXT
        );
    """)
    return conn


def _migrated_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "labeco2.sqlite"
    migrate_project_to_sqlite(ROOT, db_path)
    return db_path


# ---------------------------------------------------------------------------
# Tests unitaires de _prepare_revision
# ---------------------------------------------------------------------------

def test_prepare_revision_nonexistent_id_returns_same():
    conn = _minimal_db()
    new_id, old_id = _prepare_revision(conn, "emission_factors", "does-not-exist")
    assert new_id == "does-not-exist"
    assert old_id is None


def test_prepare_revision_draft_returns_same_id():
    conn = _minimal_db()
    conn.execute(
        "INSERT INTO emission_factors(id, name, name_key, status) VALUES(?,?,?,?)",
        ("ef-01", "Facteur draft", "facteur draft", "draft"),
    )
    new_id, old_id = _prepare_revision(conn, "emission_factors", "ef-01")
    assert new_id == "ef-01"
    assert old_id is None
    status = conn.execute("SELECT status FROM emission_factors WHERE id='ef-01'").fetchone()[0]
    assert status == "draft"


def test_prepare_revision_validated_deprecates_old_and_returns_new_id():
    conn = _minimal_db()
    conn.execute(
        "INSERT INTO emission_factors(id, name, name_key, status) VALUES(?,?,?,?)",
        ("ef-02", "Facteur validé", "facteur valide", "validated"),
    )
    new_id, old_id = _prepare_revision(conn, "emission_factors", "ef-02")
    assert new_id != "ef-02"
    assert old_id == "ef-02"
    row = conn.execute(
        "SELECT status, name_key FROM emission_factors WHERE id='ef-02'"
    ).fetchone()
    assert row[0] == "deprecated"
    assert ":dep:" in row[1]


def test_prepare_revision_without_name_key_col_deprecates_only_status():
    conn = _minimal_db()
    conn.execute(
        "INSERT INTO commercial_products(id, name, status) VALUES(?,?,?)",
        ("cp-01", "Produit validé", "validated"),
    )
    new_id, old_id = _prepare_revision(conn, "commercial_products", "cp-01", name_key_col=None)
    assert new_id != "cp-01"
    assert old_id == "cp-01"
    status = conn.execute(
        "SELECT status FROM commercial_products WHERE id='cp-01'"
    ).fetchone()[0]
    assert status == "deprecated"


def test_prepare_revision_validated_twice_produces_two_deprecated():
    """Deux appels successifs sur des entrées validées = deux révisions distinctes."""
    conn = _minimal_db()
    conn.execute(
        "INSERT INTO emission_factors(id, name, name_key, status) VALUES(?,?,?,?)",
        ("ef-03", "Facteur double", "facteur double", "validated"),
    )
    id_a, old_a = _prepare_revision(conn, "emission_factors", "ef-03")
    assert id_a != "ef-03"

    # Simuler l'insertion de la première révision et la valider
    conn.execute(
        "INSERT INTO emission_factors(id, name, name_key, status) VALUES(?,?,?,?)",
        (id_a, "Facteur double", "facteur double", "validated"),
    )
    id_b, old_b = _prepare_revision(conn, "emission_factors", id_a)
    assert id_b != id_a
    assert old_b == id_a

    deprecated_count = conn.execute(
        "SELECT COUNT(*) FROM emission_factors WHERE status='deprecated'"
    ).fetchone()[0]
    assert deprecated_count == 2


# ---------------------------------------------------------------------------
# Tests d'intégration via upsert (base migrée)
# ---------------------------------------------------------------------------

def test_upsert_liquid_factor_validated_creates_revision(tmp_path):
    db_path = _migrated_db(tmp_path)
    row = {
        "Produit": "Solvant révision test",
        "Type": "Liquide / solvant",
        "Code NACRES": "NA02",
        "Unité": "mL",
        "Densité (g/mL)": "0.9",
        "Facteur CO₂ (kg CO₂e/kg)": "2.5",
        "Incertitude (%)": "10",
        "Source": "Source rev",
        "Signature": "Testeur",
        "date d'ajout": "2026-05-18",
    }
    factor_id = upsert_liquid_factor(db_path, row)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE emission_factors SET status='validated' WHERE id=?", (factor_id,)
        )

    new_id = upsert_liquid_factor(db_path, row)
    assert new_id != factor_id

    with sqlite3.connect(db_path) as conn:
        old_status = conn.execute(
            "SELECT status FROM emission_factors WHERE id=?", (factor_id,)
        ).fetchone()[0]
        new_row = conn.execute(
            "SELECT status, revision_of_id FROM emission_factors WHERE id=?", (new_id,)
        ).fetchone()

    assert old_status == "deprecated"
    assert new_row[0] == "draft"
    assert new_row[1] == factor_id


def test_upsert_material_factor_validated_creates_revision(tmp_path):
    db_path = _migrated_db(tmp_path)
    row = {
        "Materiau": "Matériau révision test",
        "Equivalent CO₂ (kg eCO₂/kg)": "3.0",
        "uncertainty": "0.1",
        "Source": "Source rev mat",
        "Signature": "Testeur",
    }
    upsert_material_factor(db_path, row)

    with sqlite3.connect(db_path) as conn:
        mat_id = conn.execute(
            "SELECT id FROM materials WHERE name = ?", ("Matériau révision test",)
        ).fetchone()[0]
        ef_id = conn.execute(
            "SELECT emission_factor_id FROM materials WHERE id=?", (mat_id,)
        ).fetchone()[0]
        conn.execute("UPDATE emission_factors SET status='validated' WHERE id=?", (ef_id,))
        conn.execute("UPDATE materials SET status='validated' WHERE id=?", (mat_id,))

    upsert_material_factor(db_path, row)

    with sqlite3.connect(db_path) as conn:
        ef_status = conn.execute(
            "SELECT status FROM emission_factors WHERE id=?", (ef_id,)
        ).fetchone()[0]
        mat_status = conn.execute(
            "SELECT status FROM materials WHERE id=?", (mat_id,)
        ).fetchone()[0]
        new_mat_count = conn.execute(
            "SELECT COUNT(*) FROM materials WHERE revision_of_id=?", (mat_id,)
        ).fetchone()[0]

    assert ef_status == "deprecated"
    assert mat_status == "deprecated"
    assert new_mat_count == 1
