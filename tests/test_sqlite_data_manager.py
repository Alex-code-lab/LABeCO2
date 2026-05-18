# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests de lecture applicative depuis la base SQLite migrée."""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools.migrate_hdf5_to_sqlite import migrate_project_to_sqlite
from ui.data_manager import DataManager


ROOT_DIR = Path(__file__).resolve().parents[1]


def _sqlite_data_manager(tmp_path):
    db_path = tmp_path / "labeco2.sqlite"
    migrate_project_to_sqlite(ROOT_DIR, db_path)
    return DataManager(str(ROOT_DIR), user_path=str(ROOT_DIR), sqlite_path=db_path)


def test_data_manager_can_load_legacy_frames_from_sqlite(tmp_path):
    dm = _sqlite_data_manager(tmp_path)

    assert len(dm.get_main_data()) > 1000
    assert len(dm.get_data_masse()) > 900
    assert len(dm.get_data_materials()) >= 10
    assert len(dm.get_data_liquides()) >= 30
    assert len(dm.data_transport) >= 5


def test_data_manager_can_use_sqlite_env_var(tmp_path, monkeypatch):
    db_path = tmp_path / "labeco2.sqlite"
    migrate_project_to_sqlite(ROOT_DIR, db_path)
    monkeypatch.setenv(DataManager.SQLITE_ENV_VAR, str(db_path))

    dm = DataManager(str(ROOT_DIR), user_path=str(ROOT_DIR))

    assert len(dm.get_data_masse()) > 900


def test_sqlite_data_manager_resolves_commercial_liquid_factor(tmp_path):
    dm = _sqlite_data_manager(tmp_path)

    product_row, factor_row = dm.get_consumable_liquid_factor_data(
        "NA02",
        "ACETONE NP 1 litre",
    )

    assert product_row is not None
    assert factor_row is not None
    assert product_row["Facteur liquide source"] == factor_row["Produit"]
    assert product_row["Volume flacon (mL)"] == 1000.0


def test_sqlite_data_manager_keeps_capacity_object_as_solid(tmp_path):
    dm = _sqlite_data_manager(tmp_path)
    df = dm.get_data_masse()
    row = df[df["Consommable"].str.startswith("BOITE à DÉCHETS 300ml")].iloc[0]

    assert row["Volume flacon (mL)"] == 300.0
    assert row["Unité liquide"] == ""
    assert not dm.is_liquid_commercial_row(row)
