# SPDX-License-Identifier: GPL-3.0-or-later
"""
Fixtures partagées pour la suite de tests LABeCO2.

Problème : docs/test_carbon_calculator_annote.py injecte sys.modules['tables'] = MagicMock()
au niveau module pour éviter d'importer pytables dans un environnement sans écran.
Ce mock polluait tous les tests suivants qui appellent pandas.io.pytables (migration HDF5).
Ce fixture autouse le retire avant chaque test de ce répertoire et le remet après.
"""
import sys
from unittest.mock import MagicMock

import pytest

_MOCKED_BY_DOCS = ("tables", "tables.flavor")


def _drop_mocked_tables_modules():
    for mod in _MOCKED_BY_DOCS:
        module = sys.modules.get(mod)
        if module is None:
            continue
        if isinstance(module, MagicMock) or (mod == "tables" and not hasattr(module, "filters")):
            sys.modules.pop(mod, None)


@pytest.fixture(autouse=True)
def _isolate_tables_mock():
    """Retire les faux modules 'tables' injectés par certains tests UI."""
    _drop_mocked_tables_modules()
    yield
    _drop_mocked_tables_modules()
