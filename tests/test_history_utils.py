# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_history_utils.py
#
# Tests unitaires pour ui/charts/history_utils.py.
# Les widgets Qt sont simulés par de simples objets Python.

import sys
import os
import unittest
from unittest.mock import MagicMock

# Neutraliser PySide6
for _mod in ['PySide6', 'PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtCore.Qt']:
    sys.modules.setdefault(_mod, MagicMock())

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ui.charts.history_utils import iter_history_data


# ── Simulateurs de widgets Qt ─────────────────────────────────────────────────

class _FakeItem:
    """Simule QTableWidgetItem / QListWidgetItem."""
    def __init__(self, data=None):
        self._data = data

    def data(self, role):
        return self._data


class _FakeTableWidget:
    """Simule QTableWidget (rowCount + item(row, col))."""
    def __init__(self, rows):
        # rows : liste de dicts ou None (None = item absent)
        self._rows = rows

    def rowCount(self):
        return len(self._rows)

    def item(self, row, col):
        if col != 0:
            return None
        d = self._rows[row]
        return None if d is None else _FakeItem(d)


class _FakeListWidget:
    """Simule QListWidget (count + item(index))."""
    def __init__(self, items):
        self._items = items

    def count(self):
        return len(self._items)

    def item(self, index):
        d = self._items[index]
        return None if d is None else _FakeItem(d)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestIterHistoryData(unittest.TestCase):

    def test_none_ne_yielde_rien(self):
        self.assertEqual(list(iter_history_data(None)), [])

    def test_table_widget_nominal(self):
        d1 = {"category": "Achats", "emissions_price": 1.5}
        d2 = {"category": "Véhicules", "emissions_price": 2.0}
        result = list(iter_history_data(_FakeTableWidget([d1, d2])))
        self.assertEqual(result, [d1, d2])

    def test_table_widget_vide(self):
        self.assertEqual(list(iter_history_data(_FakeTableWidget([]))), [])

    def test_table_widget_item_none_ignore(self):
        """Une ligne dont item() retourne None doit être sautée."""
        d = {"category": "Achats"}
        result = list(iter_history_data(_FakeTableWidget([None, d])))
        self.assertEqual(result, [d])

    def test_table_widget_data_falsy_ignore(self):
        """Une ligne dont item.data() retourne None/vide doit être sautée."""
        widget = _FakeTableWidget([None])
        self.assertEqual(list(iter_history_data(widget)), [])

    def test_list_widget_fallback(self):
        """QListWidget (count + item) doit fonctionner en fallback."""
        d1 = {"category": "Machine"}
        d2 = {"category": "Achats"}
        result = list(iter_history_data(_FakeListWidget([d1, d2])))
        self.assertEqual(result, [d1, d2])

    def test_list_widget_item_none_ignore(self):
        d = {"category": "Machine"}
        result = list(iter_history_data(_FakeListWidget([None, d])))
        self.assertEqual(result, [d])

    def test_list_widget_vide(self):
        self.assertEqual(list(iter_history_data(_FakeListWidget([]))), [])

    def test_table_widget_prioritaire_sur_list(self):
        """rowCount doit être détecté avant count (QTableWidget > QListWidget)."""
        d = {"category": "Achats"}
        widget = _FakeTableWidget([d])
        widget.count = lambda: 99   # attribut parasite
        result = list(iter_history_data(widget))
        self.assertEqual(result, [d])   # pas 99 items

    def test_ordre_preserve(self):
        """L'ordre des lignes doit être conservé."""
        data = [{"i": i} for i in range(5)]
        result = list(iter_history_data(_FakeTableWidget(data)))
        self.assertEqual([d["i"] for d in result], [0, 1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()
