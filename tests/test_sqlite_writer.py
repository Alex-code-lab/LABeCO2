# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests des écritures SQLite utilisées par les formulaires."""

import os
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ui.data_manager import DataManager
from ui.sqlite_writer import (
    upsert_commercial_product,
    upsert_liquid_factor,
    upsert_material_factor,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
_REFERENCE_DB = ROOT_DIR / "data" / "labeco2_reference.sqlite"


def _migrated_db(tmp_path):
    db_path = tmp_path / "labeco2.sqlite"
    shutil.copy(_REFERENCE_DB, db_path)
    return db_path


def test_sqlite_writer_adds_liquid_factor_and_linked_commercial_product(tmp_path):
    db_path = _migrated_db(tmp_path)

    upsert_liquid_factor(
        db_path,
        {
            "Produit": "Solvant test migration",
            "Type": "Liquide / solvant",
            "Code NACRES": "NA02",
            "Unité": "mL",
            "Densité (g/mL)": "0.95",
            "Concentration (mg/mL)": "",
            "Facteur CO₂ (kg CO₂e/kg)": "3.2",
            "Incertitude (%)": "12",
            "Source": "Source test",
            "Signature": "Equipe test",
            "date d'ajout": "2026-05-18",
        },
    )
    upsert_commercial_product(
        db_path,
        {
            "Consommable": "Produit liquide test SQLite",
            "Marque": "Marque test",
            "Référence": "REF-SQL-LIQ",
            "Catégorie": "Consommable",
            "Code NACRES": "NA02",
            "Nbr par conditionnement": 6,
            "Prix du conditionnement": 72.0,
            "Unité liquide": "mL",
            "Volume flacon (mL)": 500,
            "Facteur liquide source": "Solvant test migration",
            "Source": "Source test",
            "Signature": "Equipe test",
            "date d'ajout": "2026-05-18",
        },
    )

    dm = DataManager(str(ROOT_DIR), user_path=str(ROOT_DIR), sqlite_path=db_path)
    product_row, factor_row = dm.get_consumable_liquid_factor_data(
        "NA02",
        "Produit liquide test SQLite",
    )

    assert product_row is not None
    assert factor_row is not None
    assert factor_row["Produit"] == "Solvant test migration"
    assert product_row["Volume flacon (mL)"] == 500.0


def test_sqlite_writer_updates_existing_product_without_duplicate(tmp_path):
    """Modifier un produit validé crée une révision draft + déprécie l'original.
    Le résultat attendu : 2 lignes (1 deprecated + 1 draft avec le nouveau prix)."""
    db_path = _migrated_db(tmp_path)
    row = {
        "Consommable": "Produit solide test SQLite",
        "Marque": "Marque test",
        "Référence": "REF-SQL-SOLID",
        "Catégorie": "Consommable",
        "Code NACRES": "NB11",
        "Masse unitaire (g)": 12,
        "Matériau consommable": "Polypropylène (PP)",
        "Nbr par conditionnement": 100,
        "Prix du conditionnement": 40,
        "Source": "Source test",
        "Signature": "Equipe test",
        "date d'ajout": "2026-05-18",
    }

    product_id = upsert_commercial_product(db_path, row)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE commercial_products SET status='validated' WHERE id=?",
            (product_id,),
        )

    updated = dict(row)
    updated["Prix du conditionnement"] = 55
    new_id = upsert_commercial_product(db_path, updated, existing_id=product_id)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, status, price_sold_packaging FROM commercial_products"
            " WHERE reference = 'REF-SQL-SOLID'"
        ).fetchall()

    assert len(rows) == 2, "Attendu : 1 deprecated + 1 draft (révision)"
    statuses = {r[0]: r[1] for r in rows}
    prices = {r[0]: r[2] for r in rows}
    assert statuses[product_id] == "deprecated"
    assert statuses[new_id] == "draft"
    assert prices[new_id] == 55

    dm = DataManager(str(ROOT_DIR), user_path=str(ROOT_DIR), sqlite_path=db_path)
    visible = dm.data_masse[
        dm.data_masse["Référence"].astype(str) == "REF-SQL-SOLID"
    ]
    assert len(visible) == 1
    assert visible.iloc[0]["Prix du conditionnement"] == 55


def test_sqlite_writer_new_user_entries_are_drafts(tmp_path):
    db_path = _migrated_db(tmp_path)

    factor_id = upsert_liquid_factor(
        db_path,
        {
            "Produit": "Solvant draft test",
            "Type": "Liquide / solvant",
            "Code NACRES": "NA02",
            "Densité (g/mL)": "0.9",
            "Facteur CO₂ (kg CO₂e/kg)": "2.5",
            "Source": "Source draft",
            "Signature": "Equipe test",
        },
    )
    product_id = upsert_commercial_product(
        db_path,
        {
            "Consommable": "Produit draft test",
            "Marque": "Marque test",
            "Référence": "REF-DRAFT",
            "Catégorie": "Consommable",
            "Code NACRES": "NA02",
            "Nbr par conditionnement": 1,
            "Prix du conditionnement": 10,
            "Unité liquide": "mL",
            "Volume flacon (mL)": 100,
            "Facteur liquide source": "Solvant draft test",
            "Source": "Source draft",
            "Signature": "Equipe test",
        },
    )

    with sqlite3.connect(db_path) as conn:
        factor_status = conn.execute(
            "SELECT status FROM emission_factors WHERE id=?", (factor_id,)
        ).fetchone()[0]
        product_status = conn.execute(
            "SELECT status FROM commercial_products WHERE id=?", (product_id,)
        ).fetchone()[0]

    assert factor_status == "draft"
    assert product_status == "draft"


def test_sqlite_writer_persists_product_note(tmp_path):
    db_path = _migrated_db(tmp_path)
    product_id = upsert_commercial_product(
        db_path,
        {
            "Consommable": "Produit note test",
            "Marque": "Marque test",
            "Référence": "REF-NOTE",
            "Catégorie": "Consommable",
            "Code NACRES": "NB11",
            "Masse unitaire (g)": 12,
            "Matériau consommable": "Polypropylène (PP)",
            "Nbr par conditionnement": 1,
            "Prix du conditionnement": 10,
            "Source": "Source note",
            "Signature": "Equipe test",
            "Lien / Note / Remarque": "https://example.org/notice ; prix catalogue vérifié",
        },
    )

    with sqlite3.connect(db_path) as conn:
        note = conn.execute(
            "SELECT note FROM commercial_products WHERE id=?", (product_id,)
        ).fetchone()[0]

    dm = DataManager(str(ROOT_DIR), user_path=str(ROOT_DIR), sqlite_path=db_path)
    row = dm.data_masse[dm.data_masse["Référence"].astype(str) == "REF-NOTE"].iloc[0]

    assert note == "https://example.org/notice ; prix catalogue vérifié"
    assert row["Lien / Note / Remarque"] == note


def test_sqlite_writer_liquid_factor_name_change_uses_existing_id_revision(tmp_path):
    db_path = _migrated_db(tmp_path)
    row = {
        "Produit": "Solvant renommage test",
        "Type": "Liquide / solvant",
        "Code NACRES": "NA02",
        "Densité (g/mL)": "0.9",
        "Facteur CO₂ (kg CO₂e/kg)": "2.5",
        "Source": "Source renommage",
        "Signature": "Equipe test",
    }
    factor_id = upsert_liquid_factor(db_path, row)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE emission_factors SET status='validated' WHERE id=?",
            (factor_id,),
        )

    updated = dict(row)
    updated["Produit"] = "Solvant renommé test"
    new_id = upsert_liquid_factor(db_path, updated, existing_id=factor_id)

    with sqlite3.connect(db_path) as conn:
        old_status = conn.execute(
            "SELECT status FROM emission_factors WHERE id=?", (factor_id,)
        ).fetchone()[0]
        new_status, revision_of = conn.execute(
            "SELECT status, revision_of_id FROM emission_factors WHERE id=?", (new_id,)
        ).fetchone()

    assert old_status == "deprecated"
    assert new_status == "draft"
    assert revision_of == factor_id


def test_sqlite_writer_skips_components_without_mass(tmp_path):
    db_path = _migrated_db(tmp_path)
    product_id = upsert_commercial_product(
        db_path,
        {
            "Consommable": "Produit sans masse composant",
            "Marque": "Marque test",
            "Référence": "REF-SQL-NOMASS",
            "Catégorie": "Consommable",
            "Code NACRES": "AA01",
            "Matériau consommable": "Polypropylène (PP)",
            "Matériau conditionnement": "Papier",
            "Nbr par conditionnement": 50,
            "Prix du conditionnement": 12,
            "Source": "Source test",
            "Signature": "Equipe test",
            "date d'ajout": "2026-05-18",
        },
    )

    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM product_components WHERE product_id = ?",
            (product_id,),
        ).fetchone()[0]

    assert count == 0


def test_sqlite_writer_adds_material_factor(tmp_path):
    db_path = _migrated_db(tmp_path)

    upsert_material_factor(
        db_path,
        {
            "Materiau": "Matériau test SQLite",
            "Equivalent CO₂ (kg eCO₂/kg)": "4.5",
            "uncertainty": "0.2",
            "Source": "Source matériau test",
            "Signature": "Equipe test",
        },
    )

    dm = DataManager(str(ROOT_DIR), user_path=str(ROOT_DIR), sqlite_path=db_path)
    co2, uncertainty = dm.get_material_data("Matériau test SQLite")

    assert co2 == 4.5
    assert uncertainty == 0.2
