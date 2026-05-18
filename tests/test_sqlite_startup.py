# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests de résolution SQLite au démarrage."""

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.data_loader import (
    SQLITE_PATH_ENV_VAR,
    SQLITE_USE_HDF5_ENV_VAR,
    resolve_sqlite_path,
)


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_resolve_sqlite_path_creates_missing_explicit_database(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "startup.sqlite"
    monkeypatch.setenv(SQLITE_PATH_ENV_VAR, str(sqlite_path))

    resolved = resolve_sqlite_path(ROOT_DIR, ROOT_DIR)

    assert resolved == str(sqlite_path)
    assert sqlite_path.exists()
    with sqlite3.connect(sqlite_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM commercial_products").fetchone()[0]
    assert count > 900


def test_resolve_sqlite_path_can_force_hdf5_mode(tmp_path, monkeypatch):
    monkeypatch.setenv(SQLITE_PATH_ENV_VAR, str(tmp_path / "startup.sqlite"))
    monkeypatch.setenv(SQLITE_USE_HDF5_ENV_VAR, "1")

    assert resolve_sqlite_path(ROOT_DIR, ROOT_DIR) is None
