# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_data_mass_window_logic.py
#
# Tests ciblés de la logique métier de DataMassWindow sans ouvrir de fenêtre Qt.

import os
import sys
import types
import unittest
from unittest.mock import MagicMock

import pandas as pd


class _FakeQMainWindow:
    def __init__(self, *args, **kwargs):
        pass


class _FakeSignal:
    def __init__(self, *args, **kwargs):
        self.emit = MagicMock()


class _FakeLineEdit:
    def __init__(self, text=""):
        self._text = str(text)
        self._hidden = False

    def text(self):
        return self._text

    def setText(self, value):
        self._text = str(value)

    def clear(self):
        self._text = ""

    def setValidator(self, *args, **kwargs):
        pass

    def setPlaceholderText(self, *args, **kwargs):
        pass

    def setStyleSheet(self, *args, **kwargs):
        pass

    def setVisible(self, visible):
        self._hidden = not visible

    def isHidden(self):
        return self._hidden


class _FakeComboBox:
    def __init__(self, text="", data=None, count=1):
        self._text = str(text)
        self._data = data
        self._index = 0 if count else -1
        self._count = count

    def currentData(self):
        return self._data

    def currentText(self):
        return self._text

    def setCurrentIndex(self, index):
        self._index = index

    def currentIndex(self):
        return self._index

    def count(self):
        return self._count

    def setStyleSheet(self, *args, **kwargs):
        pass


class _FakeQColor:
    def __init__(self, *args, **kwargs):
        self._args = args

    def name(self):
        return "#000000"


class _FakeQMessageBox:
    warning = MagicMock()
    information = MagicMock()
    critical = MagicMock()
    question = MagicMock()
    Yes = 1
    No = 0


_qtwidgets = types.ModuleType("PySide6.QtWidgets")
_qtwidgets.QMainWindow = _FakeQMainWindow
_qtwidgets.QMessageBox = _FakeQMessageBox
_qtwidgets.QLineEdit = _FakeLineEdit
_qtwidgets.QComboBox = _FakeComboBox
_qtwidgets.QWidget = type("QWidget", (), {})
_qtwidgets.QVBoxLayout = type("QVBoxLayout", (), {})
_qtwidgets.QFormLayout = type("QFormLayout", (), {})
_qtwidgets.QPushButton = type("QPushButton", (), {})
_qtwidgets.QTableWidget = type("QTableWidget", (), {})
_qtwidgets.QTableWidgetItem = type("QTableWidgetItem", (), {})
_qtwidgets.QHBoxLayout = type("QHBoxLayout", (), {})
_qtwidgets.QLabel = type("QLabel", (), {})
_qtwidgets.QFileDialog = type("QFileDialog", (), {})
_qtwidgets.QToolTip = type("QToolTip", (), {})
_qtwidgets.QScrollArea = type("QScrollArea", (), {})
_qtwidgets.QSizePolicy = type("QSizePolicy", (), {})

_qtcore = types.ModuleType("PySide6.QtCore")
_qtcore.Signal = _FakeSignal
_qtcore.Qt = types.SimpleNamespace()

_qtgui = types.ModuleType("PySide6.QtGui")
_qtgui.QColor = _FakeQColor
_qtgui.QCursor = type("QCursor", (), {})
_qtgui.QDoubleValidator = type("QDoubleValidator", (), {"__init__": lambda self, *a, **k: None})
_qtgui.QIntValidator = type("QIntValidator", (), {"__init__": lambda self, *a, **k: None})

sys.modules["PySide6"] = types.ModuleType("PySide6")
sys.modules["PySide6.QtWidgets"] = _qtwidgets
sys.modules["PySide6.QtCore"] = _qtcore
sys.modules["PySide6.QtGui"] = _qtgui
sys.modules.pop("ui.data_mass_window", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ui import data_mass_window as data_mass_window_module
from ui.data_mass_window import DataMassWindow

# Le module testé garde ses références vers les faux widgets importés ci-dessus.
# On nettoie sys.modules pour ne pas polluer les tests suivants qui importent
# d'autres parties de l'application avec le vrai PySide6.
for _qt_mod in ("PySide6", "PySide6.QtWidgets", "PySide6.QtCore", "PySide6.QtGui"):
    sys.modules.pop(_qt_mod, None)


SOLID_COLUMNS = [
    "Consommable", "Marque", "Référence", "Code CAS", "Catégorie",
    "Code NACRES", "Masse unitaire (g)", "Matériau consommable",
    "Masse unitaire deuxieme materiaux (g)", "Matériau deuxieme materiaux",
    "Masse unitaire troisième materiaux (g)", "Matériau troisième materiaux",
    "Masse emballage unitaire (g)", "Matériau emballage",
    "Masse condionnement (g)", "Matériau conditionnement",
    "Nbr par conditionnement", "Prix du conditionnement", "Unité liquide",
    "Volume flacon (mL)", "Facteur liquide source", "date d'ajout",
    "Source", "Signature", "Source catalogue IJM", "Lien / Note / Remarque",
    "condt_ijm", "designation_ijm", "code_ijm", "marque_ijm", "score_match",
]

LIQUID_COLUMNS = [
    "Produit", "Type", "Code NACRES", "CAS", "Référence", "Unité",
    "Densité (g/mL)", "Concentration (mg/mL)",
    "Facteur CO₂ (kg CO₂e/kg)", "Incertitude (%)",
    "Source", "Signature", "date d'ajout", "Note",
]


def _reset_message_boxes():
    data_mass_window_module.QMessageBox.warning.reset_mock()
    data_mass_window_module.QMessageBox.information.reset_mock()
    data_mass_window_module.QMessageBox.critical.reset_mock()


def _line(text=""):
    return _FakeLineEdit(text)


def _combo(text="", data=None):
    return _FakeComboBox(text=text, data=data)


def _make_window(
    *,
    mode=DataMassWindow.MODE_LIQUID_CONSUMABLE,
    liquid_factor_data="Acétone",
    nbr_cond="1",
    price="60",
    price_mode=None,
    liquid_volume="1000",
    manual_factor_name="",
    dens="0.79",
    facteur="2.5",
    source="Article source",
    signature="Equipe test",
):
    win = DataMassWindow.__new__(DataMassWindow)
    win.columns = SOLID_COLUMNS
    win.columns_liquids = LIQUID_COLUMNS
    win.columns_materials = [
        "Materiau", "Equivalent CO₂ (kg eCO₂/kg)", "uncertainty", "Source", "Signature",
    ]
    win.data = pd.DataFrame(columns=SOLID_COLUMNS)
    win.required_fields = []
    win.prefill_row_index = None
    win._prefill_liq_produit = None
    win.type_combo = _combo(data=mode)

    win.nom_input = _line("Produit commercial utilisateur")
    win.brand_input = _line("Marque utilisateur")
    win.ref_input = _line("REF-USER")
    win.masse_input = _line("")
    win.masse2_input = _line("")
    win.masse_emb_input = _line("")
    win.masse_cond_input = _line("")
    win.nbr_cond_input = _line(nbr_cond)
    win.price_input = _line(price)
    win.manual_liquid_factor_name_input = _line(manual_factor_name)
    win.solid_liquid_volume_input = _line(liquid_volume)
    win.lien_input = _line("")
    win.source_input = _line(source)
    win.signature_input = _line(signature)
    win.dens_input = _line(dens)
    win.conc_input = _line("")
    win.factor_input = _line(facteur)
    win.uncert_input = _line("10")
    win.vol_flacon_input = _line("")
    win.masse_contenant_liq_input = _line("")
    win.masse_emb_liq_input = _line("")

    win.nacres_combo = _combo(text="LA01 - Liquides", data="LA01")
    win.materiau_combo = _combo(text="Polypropylène (PP)", data="Polypropylène (PP)")
    win.materiau2_combo = _combo(text="", data="")
    win.mat_emb_combo = _combo(text="", data="")
    win.mat_cond_combo = _combo(text="", data="")
    win.mat_contenant_liq_combo = _combo(text="", data="")
    win.mat_emb_liq_combo = _combo(text="", data="")
    win.price_mode_combo = _combo(
        text=price_mode or DataMassWindow.PRICE_MODE_PACK,
        data=price_mode or DataMassWindow.PRICE_MODE_PACK,
    )
    win.liquid_factor_combo = _combo(text=str(liquid_factor_data), data=liquid_factor_data)
    win.liquid_copy_factor_combo = _combo(text="", data=None)

    win.sauvegarder_donnees = MagicMock()
    win.save_liquid = MagicMock()
    win.afficher_donnees = MagicMock()
    win.update_action_button_text = MagicMock()
    win.update_price_preview = MagicMock()
    win.data_added = types.SimpleNamespace(emit=MagicMock())
    return win


class TestDataMassWindowLiquidConsumableValidation(unittest.TestCase):

    def setUp(self):
        _reset_message_boxes()

    def test_liquid_consumable_requires_existing_or_manual_factor(self):
        win = _make_window(liquid_factor_data="")

        win.ajouter_objet_utilisateur()

        data_mass_window_module.QMessageBox.warning.assert_called_once()
        self.assertEqual(
            data_mass_window_module.QMessageBox.warning.call_args.args[1],
            "Facteur liquide / solvant requis",
        )
        win.sauvegarder_donnees.assert_not_called()
        self.assertTrue(win.data.empty)

    def test_manual_liquid_factor_requires_complete_factor_fields(self):
        win = _make_window(
            liquid_factor_data="__manual__",
            manual_factor_name="Acétone",
            dens="",
        )

        win.ajouter_objet_utilisateur()

        data_mass_window_module.QMessageBox.warning.assert_called_once()
        self.assertEqual(
            data_mass_window_module.QMessageBox.warning.call_args.args[1],
            "Nouveau facteur incomplet",
        )
        self.assertIn("densité", data_mass_window_module.QMessageBox.warning.call_args.args[2])
        win.save_liquid.assert_not_called()
        win.sauvegarder_donnees.assert_not_called()

    def test_liquid_pack_over_one_warns_that_volume_is_per_sold_unit(self):
        win = _make_window(nbr_cond="6", liquid_factor_data="Acétone")

        win.ajouter_objet_utilisateur()

        information_titles = [
            call.args[1]
            for call in data_mass_window_module.QMessageBox.information.call_args_list
        ]
        self.assertIn("Volume par unité vendue", information_titles)
        win.sauvegarder_donnees.assert_called_once()
        saved_row = win.data.iloc[0]
        self.assertEqual(saved_row["Consommable"], "Produit commercial utilisateur")
        self.assertEqual(saved_row["Facteur liquide source"], "Acétone")
        self.assertEqual(saved_row["Nbr par conditionnement"], 6)
        self.assertEqual(saved_row["Volume flacon (mL)"], "1000")

    def test_manual_liquid_factor_saves_factor_and_keeps_commercial_product_identity(self):
        win = _make_window(
            liquid_factor_data="__manual__",
            manual_factor_name="Acétone",
            nbr_cond="1",
            liquid_volume="500",
        )

        win.ajouter_objet_utilisateur()

        win.save_liquid.assert_called_once()
        factor_row = win.save_liquid.call_args.args[0]
        self.assertEqual(factor_row["Produit"], "Acétone")
        self.assertEqual(factor_row["Référence"], "")

        saved_row = win.data.iloc[0]
        self.assertEqual(saved_row["Consommable"], "Produit commercial utilisateur")
        self.assertEqual(saved_row["Référence"], "REF-USER")
        self.assertEqual(saved_row["Facteur liquide source"], "Acétone")
        self.assertEqual(saved_row["Volume flacon (mL)"], "500")

    def test_price_per_sold_unit_is_converted_to_pack_price(self):
        win = _make_window(
            nbr_cond="4",
            price="12.5",
            price_mode=DataMassWindow.PRICE_MODE_UNIT,
        )

        win.ajouter_objet_utilisateur()

        saved_row = win.data.iloc[0]
        self.assertAlmostEqual(saved_row["Prix du conditionnement"], 50.0)


class TestDataMassWindowDisplayLabels(unittest.TestCase):

    def test_internal_columns_have_clear_display_labels(self):
        win = DataMassWindow.__new__(DataMassWindow)

        labels = win.display_column_labels([
            "Masse condionnement (g)",
            "Nbr par conditionnement",
            "Volume flacon (mL)",
            "Colonne inconnue",
        ])

        self.assertEqual(labels[0], "Masse du conditionnement primaire complet ou du contenant vide (g)")
        self.assertEqual(labels[1], "Unités par conditionnement vendu")
        self.assertEqual(labels[2], "Volume vendu par unité de consommable (mL)")
        self.assertEqual(labels[3], "Colonne inconnue")
