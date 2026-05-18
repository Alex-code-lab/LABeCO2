# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_main_window_logic.py
#
# Tests des méthodes logiques et UI de MainWindow.
# Tous les widgets Qt sont mockés — aucune app Qt ni fichier HDF5 requis.

import sys
import os
import unittest
from unittest.mock import MagicMock
import pandas as pd

# ── QMainWindow doit être un vrai type Python pour que MainWindow puisse en
#    hériter et que __new__ fonctionne. On construit les modules Qt manuellement
#    avant tout import de code applicatif. ─────────────────────────────────────

class _FakeQMainWindow:
    """Stub minimal pour remplacer QMainWindow comme classe de base."""
    def __init__(self, *a, **kw):
        pass

_mock_qtwidgets = MagicMock()
_mock_qtwidgets.QMainWindow = _FakeQMainWindow

_mock_qtcore = MagicMock()
_mock_qtcore.Signal = MagicMock(return_value=None)
_mock_qtcore.Qt = MagicMock()

# Force-overwrite (pas setdefault) : d'autres fichiers de test importés avant
# celui-ci ont peut-être déjà mis un MagicMock() générique dans PySide6.QtWidgets.
# Il faut impérativement que QMainWindow soit un vrai type au moment où
# ui.main_window sera importé ci-dessous.
sys.modules['PySide6.QtWidgets'] = _mock_qtwidgets
sys.modules['PySide6.QtCore']    = _mock_qtcore

# Si ui.main_window était déjà dans le cache (même import partiel), on le retire
# pour qu'il soit réimporté avec les bons mocks.
sys.modules.pop('ui.main_window', None)

_OTHER_MOCKED = [
    'PySide6', 'PySide6.QtGui', 'PySide6.QtCharts', 'PySide6.QtPrintSupport',
    'shiboken6',
    'tables', 'tables.flavor',
    'utils.data_loader', 'utils.color_utils',
    'scenarios', 'scenarios.manip_type_db',
    'ui.charts', 'ui.charts.pie_chart', 'ui.charts.bar_chart_price_mass',
    'ui.charts.bar_chart_proportional', 'ui.charts.bar_chart_consumables',
    'ui.charts.nacres_bar_chart', 'ui.charts.pareto_chart',
    'ui.charts.transport_chart', 'ui.charts.transport_consumable_chart',
    'ui.charts.transport_factor_chart', 'ui.charts.transport_scenario_chart',
    'ui.charts.transport_top_chart', 'ui.charts.nacres_proportional',
    'ui.charts.coverage_overview', 'ui.charts.coverage_by_category',
    'ui.data_mass_window', 'ui.edit_calculation_dialog', 'ui.user_manip_dialog',
    'ui.charts.history_utils',
]
for _mod in _OTHER_MOCKED:
    sys.modules.setdefault(_mod, MagicMock())

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ui.main_window import MainWindow

# Retirer du cache les modules qui ne sont pas des dépendances Qt et que
# d'autres fichiers de test doivent pouvoir importer comme vrais modules.
# (ex. test_manip_type_db.py importe scenarios.manip_type_db réel)
for _mod in ('scenarios', 'scenarios.manip_type_db', 'utils.data_loader', 'utils.color_utils'):
    sys.modules.pop(_mod, None)


# ── Helpers partagés ─────────────────────────────────────────────────────────

def _make_mock_dm():
    """DataManager mocké avec toutes les constantes de colonnes."""
    dm = MagicMock()
    dm.CODE_NACRES_COL              = 'Code NACRES'
    dm.CONSOMMABLE_COL              = 'Consommable'
    dm.MASSE_G_COL                  = 'Masse unitaire (g)'
    dm.MATERIAU_COL                 = 'Matériau consommable'
    dm.MASSE_EMBALLAGE_COL          = 'Masse emballage unitaire (g)'
    dm.MATERIAU_EMBALLAGE_COL       = 'Matériau emballage'
    dm.MASSE_CONDITIONNEMENT_COL    = 'Masse condionnement (g)'
    dm.MATERIAU_CONDITIONNEMENT_COL = 'Matériau conditionnement'
    dm.FACTEUR_LIQUIDE_SOURCE_COL   = 'Facteur liquide source'
    dm.UNITE_LIQUIDE_COL            = 'Unité liquide'
    dm.VOLUME_FLACON_COL            = 'Volume flacon (mL)'
    dm.TRANSPORT_DEFAULT            = 'Inconnue (défaut)'
    dm.get_liquid_data.return_value  = None
    dm.get_prix_unitaire_info.return_value = None
    return dm


def _nacres_mask(series, code):
    """Réimplémentation locale du masque NACRES."""
    prefix = str(code or '').strip().upper()[:4]
    code_up = str(code or '').strip().upper()
    clean = series.fillna('').astype(str).str.strip().str.upper()
    return (clean == code_up) | (clean.str[:4] == prefix)


def _make_mw(selected=None, data_masse=None, data_manager=None):
    """MainWindow minimale sans __init__ Qt."""
    mw = MainWindow.__new__(MainWindow)

    # Widgets Qt mockés
    mw.masse_manquante_label    = MagicMock()
    mw.contenant_warning_label  = MagicMock()
    mw.quantity_label           = MagicMock()
    mw.quantity_input           = MagicMock()
    mw.fe_massique_label        = MagicMock()
    mw.fe_massique_input        = MagicMock()
    mw.prix_unitaire_label      = MagicMock()
    mw.prix_info_button         = MagicMock()
    mw.conso_filtered_combo     = MagicMock()

    # État courant
    mw._current_prix_unitaire           = None
    mw._current_prix_unitaire_info_text = ""
    mw._current_masse_unitaire_g        = None

    # DataManager et données
    mw.data_manager = data_manager if data_manager is not None else _make_mock_dm()

    _empty = pd.DataFrame(columns=[
        'Code NACRES', 'Consommable', 'Masse unitaire (g)', 'Matériau consommable',
        'Facteur liquide source', 'Unité liquide', 'Volume flacon (mL)',
        'Matériau emballage', 'Masse emballage unitaire (g)',
        'Matériau conditionnement', 'Masse condionnement (g)',
    ])
    mw.data_masse    = data_masse if data_masse is not None else _empty
    mw.data_liquides = pd.DataFrame()

    # Surcharge de _selected_consumable_data
    _sel = selected
    mw._selected_consumable_data = lambda: _sel

    # Masque NACRES (version test sans dépendance UI)
    mw._nacres_code_mask = _nacres_mask

    return mw


def _solid_row(
    code='AA01', nom='Produit test',
    masse_g=0.0, materiau='',
    facteur_liquide='', unite_liquide='', volume_flacon=0,
    mat_emb='', masse_emb=0.0,
    mat_cond='', masse_cond=0.0,
):
    """Construit un DataFrame data_masse avec une seule ligne solide."""
    return pd.DataFrame([{
        'Code NACRES':               code,
        'Consommable':               nom,
        'Masse unitaire (g)':        masse_g,
        'Matériau consommable':      materiau,
        'Facteur liquide source':    facteur_liquide,
        'Unité liquide':             unite_liquide,
        'Volume flacon (mL)':        volume_flacon,
        'Matériau emballage':        mat_emb,
        'Masse emballage unitaire (g)': masse_emb,
        'Matériau conditionnement':  mat_cond,
        'Masse condionnement (g)':   masse_cond,
    }])


# ─────────────────────────────────────────────────────────────────────────────
# Codes NACRES hors sous-catégorie Consommables
# ─────────────────────────────────────────────────────────────────────────────

class TestConsumableNacresLookup(unittest.TestCase):

    def test_detecte_code_nacres_avec_consommable(self):
        mw = _make_mw(data_masse=_solid_row(code='AA01', nom='Produit test'))
        self.assertTrue(mw._nacres_prefix_has_consumables('AA01'))
        self.assertTrue(mw._nacres_prefix_has_consumables('AA01 Pains'))
        self.assertFalse(mw._nacres_prefix_has_consumables('ZZ99'))

    def test_retrouve_ligne_achat_hors_sous_categorie_consommables(self):
        mw = _make_mw(data_masse=_solid_row(code='AA01', nom='Produit test'))
        mw.data = pd.DataFrame([
            {
                'category': 'Achats',
                'subcategory': 'Vie du laboratoire',
                'subsubcategory': 'AA01',
                'name': 'Pains, patisseries, viennoiseries congeles',
                'year': 2019,
                'unit': 'euro',
            },
            {
                'category': 'Achats',
                'subcategory': 'Consommables (Matières premières)',
                'subsubcategory': 'NB13',
                'name': 'Culture cellulaire',
                'year': 2019,
                'unit': 'euro',
            },
        ])

        row = mw._purchase_factor_row_for_nacres('AA01')
        self.assertIsNotNone(row)
        self.assertEqual(row['subcategory'], 'Vie du laboratoire')
        self.assertEqual(row['subsubcategory'], 'AA01')


# ─────────────────────────────────────────────────────────────────────────────
# _is_solid_liquid_product
# ─────────────────────────────────────────────────────────────────────────────

class TestIsSolidLiquidProduct(unittest.TestCase):

    def setUp(self):
        self.mw = _make_mw()

    def test_none_retourne_false(self):
        self.assertFalse(self.mw._is_solid_liquid_product(None))

    def test_facteur_liquide_source_renseigné_retourne_true(self):
        row = pd.Series({'Facteur liquide source': 'Éthanol',
                         'Unité liquide': '', 'Volume flacon (mL)': 0})
        self.assertTrue(self.mw._is_solid_liquid_product(row))

    def test_unite_liquide_renseignée_retourne_true(self):
        row = pd.Series({'Facteur liquide source': '',
                         'Unité liquide': 'mL', 'Volume flacon (mL)': 0,
                         'Code NACRES': 'NB22',
                         'Consommable': 'Acrylamide solution 500ml'})
        self.assertTrue(self.mw._is_solid_liquid_product(row))

    def test_volume_flacon_positif_seul_retourne_false(self):
        row = pd.Series({'Facteur liquide source': '',
                         'Unité liquide': '', 'Volume flacon (mL)': 500})
        self.assertFalse(self.mw._is_solid_liquid_product(row))

    def test_objet_solide_avec_capacite_retourne_false(self):
        row = pd.Series({'Facteur liquide source': '',
                         'Unité liquide': 'mL', 'Volume flacon (mL)': 300,
                         'Code NACRES': 'HA11',
                         'Consommable': 'BOITE à DÉCHETS 300ml'})
        self.assertFalse(self.mw._is_solid_liquid_product(row))

    def test_volume_flacon_code_na_retourne_true(self):
        row = pd.Series({'Facteur liquide source': '',
                         'Unité liquide': 'mL', 'Volume flacon (mL)': 1000,
                         'Code NACRES': 'NA21',
                         'Consommable': 'Acide acétique 1 litre'})
        self.assertTrue(self.mw._is_solid_liquid_product(row))

    def test_volume_flacon_zero_est_solide(self):
        """Régression : Volume flacon = 0 ne doit pas classifier comme liquide."""
        row = pd.Series({'Facteur liquide source': '',
                         'Unité liquide': '', 'Volume flacon (mL)': 0})
        self.assertFalse(self.mw._is_solid_liquid_product(row))

    def test_row_completement_vide_est_solide(self):
        self.assertFalse(self.mw._is_solid_liquid_product(pd.Series({})))

    def test_nan_dans_volume_est_solide(self):
        row = pd.Series({'Facteur liquide source': '',
                         'Unité liquide': '', 'Volume flacon (mL)': float('nan')})
        self.assertFalse(self.mw._is_solid_liquid_product(row))


# ─────────────────────────────────────────────────────────────────────────────
# _get_masse_unitaire_g
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMasseUnitaireG(unittest.TestCase):

    def test_source_liquid_retourne_zero(self):
        sel = {'code_nacres': 'LA01', 'consommable': 'Éthanol', 'source': 'liquid'}
        mw = _make_mw(selected=sel)
        self.assertEqual(mw._get_masse_unitaire_g(sel), 0.0)

    def test_vrac_sans_materiau_retourne_masse(self):
        sel = {'code_nacres': 'AA01', 'consommable': 'Produit test', 'source': 'solid'}
        mw = _make_mw(selected=sel, data_masse=_solid_row(masse_g=50.0, materiau=''))
        self.assertEqual(mw._get_masse_unitaire_g(sel), 50.0)

    def test_discret_avec_materiau_retourne_zero(self):
        sel = {'code_nacres': 'AA01', 'consommable': 'Produit test', 'source': 'solid'}
        mw = _make_mw(selected=sel, data_masse=_solid_row(masse_g=50.0, materiau='Plastique'))
        self.assertEqual(mw._get_masse_unitaire_g(sel), 0.0)

    def test_liquide_commercial_retourne_zero(self):
        sel = {'code_nacres': 'AA01', 'consommable': 'Produit test', 'source': 'solid'}
        mw = _make_mw(selected=sel,
                      data_masse=_solid_row(facteur_liquide='Éthanol', volume_flacon=1000))
        self.assertEqual(mw._get_masse_unitaire_g(sel), 0.0)

    def test_produit_introuvable_retourne_zero(self):
        sel = {'code_nacres': 'ZZ99', 'consommable': 'Inconnu', 'source': 'solid'}
        mw = _make_mw(selected=sel, data_masse=_solid_row(code='AA01'))
        self.assertEqual(mw._get_masse_unitaire_g(sel), 0.0)

    def test_masse_zero_retourne_zero(self):
        sel = {'code_nacres': 'AA01', 'consommable': 'Produit test', 'source': 'solid'}
        mw = _make_mw(selected=sel, data_masse=_solid_row(masse_g=0.0, materiau=''))
        self.assertEqual(mw._get_masse_unitaire_g(sel), 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# _update_masse_warning
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateMasseWarning(unittest.TestCase):

    def test_pas_de_selection_cache_les_deux_labels(self):
        mw = _make_mw(selected=None)
        mw._update_masse_warning()
        mw.masse_manquante_label.setVisible.assert_called_with(False)
        mw.contenant_warning_label.setVisible.assert_called_with(False)

    # ── source == "liquid" ────────────────────────────────────────────────────

    def test_liquide_avec_contenant_affiche_vert_seul(self):
        liq_row = pd.Series({
            'Unité': 'mL', 'Volume flacon (mL)': 500,
            'Matériau contenant': 'Verre', 'Masse contenant (g)': 120,
        })
        dm = _make_mock_dm()
        dm.get_liquid_data.return_value = liq_row
        mw = _make_mw(
            selected={'code_nacres': 'LA01', 'consommable': 'Éthanol', 'source': 'liquid'},
            data_manager=dm,
        )
        mw._update_masse_warning()

        mw.masse_manquante_label.setVisible.assert_called_with(True)
        text = mw.masse_manquante_label.setText.call_args[0][0]
        self.assertIn('✔', text)
        mw.contenant_warning_label.setVisible.assert_called_with(False)

    def test_liquide_sans_contenant_affiche_vert_et_orange(self):
        liq_row = pd.Series({
            'Unité': 'mL', 'Volume flacon (mL)': 0,
            'Matériau contenant': '', 'Masse contenant (g)': 0,
        })
        dm = _make_mock_dm()
        dm.get_liquid_data.return_value = liq_row
        mw = _make_mw(
            selected={'code_nacres': 'LA01', 'consommable': 'Éthanol', 'source': 'liquid'},
            data_manager=dm,
        )
        mw._update_masse_warning()

        mw.masse_manquante_label.setVisible.assert_called_with(True)
        mw.contenant_warning_label.setVisible.assert_called_with(True)
        orange_text = mw.contenant_warning_label.setText.call_args[0][0]
        self.assertIn('⚠', orange_text)

    def test_liquide_non_volumique_label_vert_generique(self):
        """Unité non volumique (ex. 'g') → label vert 'Données consommable disponibles'."""
        liq_row = pd.Series({
            'Unité': 'g', 'Volume flacon (mL)': 0,
            'Matériau contenant': '', 'Masse contenant (g)': 0,
        })
        dm = _make_mock_dm()
        dm.get_liquid_data.return_value = liq_row
        mw = _make_mw(
            selected={'code_nacres': 'NA73', 'consommable': 'Agar', 'source': 'liquid'},
            data_manager=dm,
        )
        mw._update_masse_warning()
        text = mw.masse_manquante_label.setText.call_args[0][0]
        self.assertIn('✔', text)
        # pas de warning contenant pour unité non volumique
        mw.contenant_warning_label.setVisible.assert_called_with(False)

    # ── source == "solid", produit absent de data_masse ──────────────────────

    def test_solide_absent_data_masse_label_orange(self):
        mw = _make_mw(
            selected={'code_nacres': 'ZZ99', 'consommable': 'Inconnu', 'source': 'solid'},
        )
        mw._update_masse_warning()
        mw.masse_manquante_label.setVisible.assert_called_with(True)
        text = mw.masse_manquante_label.setText.call_args[0][0]
        self.assertIn('⚠', text)

    # ── source == "solid", produit commercial liquide ─────────────────────────

    def test_solide_commercial_facteur_trouve_label_vert(self):
        factor_row = pd.Series({'Produit': 'Acétone'})
        dm = _make_mock_dm()
        dm.get_liquid_data.return_value = factor_row
        mw = _make_mw(
            selected={'code_nacres': 'NA02', 'consommable': 'Acétone 1L', 'source': 'solid'},
            data_masse=_solid_row(code='NA02', nom='Acétone 1L',
                                  facteur_liquide='Acétone',
                                  unite_liquide='mL', volume_flacon=1000),
            data_manager=dm,
        )
        mw._update_masse_warning()
        text = mw.masse_manquante_label.setText.call_args[0][0]
        self.assertIn('✔', text)
        mw.masse_manquante_label.setVisible.assert_called_with(True)

    def test_solide_commercial_facteur_absent_label_orange(self):
        dm = _make_mock_dm()
        dm.get_liquid_data.return_value = None
        mw = _make_mw(
            selected={'code_nacres': 'NA02', 'consommable': 'Solvant X', 'source': 'solid'},
            data_masse=_solid_row(code='NA02', nom='Solvant X',
                                  facteur_liquide='SolvantInconnu'),
            data_manager=dm,
        )
        mw._update_masse_warning()
        text = mw.masse_manquante_label.setText.call_args[0][0]
        self.assertIn('⚠', text)

    def test_solide_commercial_sans_contenant_affiche_warning_orange(self):
        """Produit liquide trouvé mais contenant non renseigné → warning orange."""
        factor_row = pd.Series({'Produit': 'Acétone'})
        dm = _make_mock_dm()
        dm.get_liquid_data.return_value = factor_row
        mw = _make_mw(
            selected={'code_nacres': 'NA02', 'consommable': 'Acétone 1L', 'source': 'solid'},
            data_masse=_solid_row(code='NA02', nom='Acétone 1L',
                                  facteur_liquide='Acétone',
                                  unite_liquide='mL', volume_flacon=1000,
                                  mat_cond='', masse_cond=0.0),
            data_manager=dm,
        )
        mw._update_masse_warning()
        mw.contenant_warning_label.setVisible.assert_called_with(True)

    def test_solide_commercial_avec_contenant_cache_warning(self):
        """Conditionnement renseigné → warning orange masqué."""
        factor_row = pd.Series({'Produit': 'Acétone'})
        dm = _make_mock_dm()
        dm.get_liquid_data.return_value = factor_row
        mw = _make_mw(
            selected={'code_nacres': 'NA02', 'consommable': 'Acétone 1L', 'source': 'solid'},
            data_masse=_solid_row(code='NA02', nom='Acétone 1L',
                                  facteur_liquide='Acétone',
                                  unite_liquide='mL', volume_flacon=1000,
                                  mat_cond='Verre', masse_cond=250.0),
            data_manager=dm,
        )
        mw._update_masse_warning()
        mw.contenant_warning_label.setVisible.assert_called_with(False)

    # ── source == "solid", objet solide discret ───────────────────────────────

    def test_solide_discret_avec_masse_label_vert(self):
        mw = _make_mw(
            selected={'code_nacres': 'AA01', 'consommable': 'Produit test', 'source': 'solid'},
            data_masse=_solid_row(masse_g=2.5, materiau='Plastique'),
        )
        mw._update_masse_warning()
        text = mw.masse_manquante_label.setText.call_args[0][0]
        self.assertIn('✔', text)

    def test_solide_sans_masse_label_orange(self):
        mw = _make_mw(
            selected={'code_nacres': 'AA01', 'consommable': 'Produit test', 'source': 'solid'},
            data_masse=_solid_row(masse_g=float('nan'), materiau=''),
        )
        mw._update_masse_warning()
        text = mw.masse_manquante_label.setText.call_args[0][0]
        self.assertIn('⚠', text)


# ─────────────────────────────────────────────────────────────────────────────
# _update_quantity_label
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateQuantityLabel(unittest.TestCase):

    def test_liquide_ml_label_affiche_unite(self):
        dm = _make_mock_dm()
        dm.get_liquid_data.return_value = pd.Series({'Unité': 'mL',
                                                     'Facteur CO₂ (kg CO₂e/kg)': 3.0})
        sel = {'code_nacres': 'LA01', 'consommable': 'Éthanol', 'source': 'liquid'}
        mw = _make_mw(selected=sel, data_manager=dm)
        mw._liquid_has_co2_factor = MagicMock(return_value=True)
        mw._update_quantity_label(sel)
        text = mw.quantity_label.setText.call_args[0][0]
        self.assertIn('mL', text)

    def test_liquide_avec_facteur_cache_champ_fe(self):
        dm = _make_mock_dm()
        dm.get_liquid_data.return_value = pd.Series({'Unité': 'mL',
                                                     'Facteur CO₂ (kg CO₂e/kg)': 3.0})
        sel = {'code_nacres': 'LA01', 'consommable': 'Éthanol', 'source': 'liquid'}
        mw = _make_mw(selected=sel, data_manager=dm)
        mw._liquid_has_co2_factor = MagicMock(return_value=True)
        mw._update_quantity_label(sel)
        mw.fe_massique_label.setVisible.assert_called_with(False)
        mw.fe_massique_input.setVisible.assert_called_with(False)

    def test_liquide_sans_facteur_affiche_champ_fe(self):
        dm = _make_mock_dm()
        dm.get_liquid_data.return_value = pd.Series({'Unité': 'mL',
                                                     'Facteur CO₂ (kg CO₂e/kg)': 0.0})
        sel = {'code_nacres': 'LA01', 'consommable': 'Éthanol', 'source': 'liquid'}
        mw = _make_mw(selected=sel, data_manager=dm)
        mw._liquid_has_co2_factor = MagicMock(return_value=False)
        mw._update_quantity_label(sel)
        mw.fe_massique_label.setVisible.assert_called_with(True)
        mw.fe_massique_input.setVisible.assert_called_with(True)

    def test_solid_vrac_masse_affiche_grammes_et_masse_stockee(self):
        """Produit vrac (masse sans matériau) → label 'g', masse mémorisée."""
        sel = {'code_nacres': 'AA01', 'consommable': 'Poudre', 'source': 'solid'}
        mw = _make_mw(selected=sel)
        mw._find_consumable_mass_row = MagicMock(return_value=None)
        mw._is_solid_liquid_product   = MagicMock(return_value=False)
        mw._get_masse_unitaire_g       = MagicMock(return_value=50.0)
        mw._update_quantity_label(sel)
        text = mw.quantity_label.setText.call_args[0][0]
        self.assertIn('g', text)
        self.assertEqual(mw._current_masse_unitaire_g, 50.0)

    def test_solid_discret_affiche_unites_et_cache_fe(self):
        """Produit discret (matériau défini, pas vrac) → 'unités', FE masqué."""
        sel = {'code_nacres': 'AA01', 'consommable': 'Tube', 'source': 'solid'}
        mw = _make_mw(selected=sel)
        mw._find_consumable_mass_row = MagicMock(return_value=None)
        mw._is_solid_liquid_product   = MagicMock(return_value=False)
        mw._get_masse_unitaire_g       = MagicMock(return_value=0.0)
        mw._update_quantity_label(sel)
        text = mw.quantity_label.setText.call_args[0][0]
        self.assertIn('unités', text)
        mw.fe_massique_label.setVisible.assert_called_with(False)
        mw.fe_massique_input.setVisible.assert_called_with(False)

    def test_solid_liquide_commercial_affiche_unite_liquide(self):
        """Solvant commercial en data_masse → label avec unité liquide."""
        solid_row = pd.Series({
            'Code NACRES': 'NA02', 'Consommable': 'Acétone 1L',
            'Facteur liquide source': 'Acétone', 'Unité liquide': 'mL',
            'Volume flacon (mL)': 1000,
        })
        sel = {'code_nacres': 'NA02', 'consommable': 'Acétone 1L', 'source': 'solid'}
        mw = _make_mw(selected=sel)
        mw._find_consumable_mass_row = MagicMock(return_value=solid_row)
        mw._is_solid_liquid_product   = MagicMock(return_value=True)
        mw._liquid_has_co2_factor      = MagicMock(return_value=True)
        mw._update_quantity_label(sel)
        text = mw.quantity_label.setText.call_args[0][0]
        self.assertIn('mL', text)
        mw.fe_massique_label.setVisible.assert_called_with(False)


# ─────────────────────────────────────────────────────────────────────────────
# _update_prix_unitaire
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdatePrixUnitaire(unittest.TestCase):

    def test_pas_de_selection_cache_label_et_bouton(self):
        mw = _make_mw(selected=None)
        mw._update_prix_unitaire()
        mw.prix_unitaire_label.setVisible.assert_called_with(False)
        mw.prix_info_button.setVisible.assert_called_with(False)
        self.assertIsNone(mw._current_prix_unitaire)

    def test_prix_trouve_rend_label_visible(self):
        dm = _make_mock_dm()
        dm.get_prix_unitaire_info.return_value = {
            'prix_unitaire': 0.14,
            'conditionnement': '1×500',
            'source_catalogue': 'Catalogue IJM 2025',
            'designation': 'Tube IJM',
            'code_ijm': 'P001',
            'marque': 'MARQUE',
            'prix_ht': 70.0,
            'nb_unites': 500,
            'score_match': '',
        }
        sel = {'code_nacres': 'NB11', 'consommable': 'Tube IJM', 'source': 'solid'}
        mw = _make_mw(selected=sel, data_manager=dm)
        mw._update_prix_unitaire()

        mw.prix_unitaire_label.setVisible.assert_called_with(True)
        mw.prix_info_button.setVisible.assert_called_with(True)
        self.assertAlmostEqual(mw._current_prix_unitaire, 0.14)
        text = mw.prix_unitaire_label.setText.call_args[0][0]
        self.assertIn('0.1400', text)

    def test_prix_absent_cache_label(self):
        dm = _make_mock_dm()
        dm.get_prix_unitaire_info.return_value = None
        sel = {'code_nacres': 'ZZ99', 'consommable': 'Produit sans prix', 'source': 'solid'}
        mw = _make_mw(selected=sel, data_manager=dm)
        mw._update_prix_unitaire()
        mw.prix_unitaire_label.setVisible.assert_called_with(False)
        self.assertIsNone(mw._current_prix_unitaire)

    def test_prix_none_dans_info_cache_label(self):
        """prix_unitaire = None dans le dict info → label masqué."""
        dm = _make_mock_dm()
        dm.get_prix_unitaire_info.return_value = {'prix_unitaire': None}
        sel = {'code_nacres': 'NB11', 'consommable': 'Tube', 'source': 'solid'}
        mw = _make_mw(selected=sel, data_manager=dm)
        mw._update_prix_unitaire()
        mw.prix_unitaire_label.setVisible.assert_called_with(False)

    def test_prix_sans_conditionnement_label_sans_pipe(self):
        """Conditionnement absent → label sans ' | Conditionnement vendu'."""
        dm = _make_mock_dm()
        dm.get_prix_unitaire_info.return_value = {
            'prix_unitaire': 5.0,
            'conditionnement': '',
            'source_catalogue': '',
            'designation': 'Produit', 'code_ijm': '', 'marque': '',
            'prix_ht': 5.0, 'nb_unites': 1, 'score_match': '',
        }
        sel = {'code_nacres': 'AA01', 'consommable': 'Produit', 'source': 'solid'}
        mw = _make_mw(selected=sel, data_manager=dm)
        mw._update_prix_unitaire()
        text = mw.prix_unitaire_label.setText.call_args[0][0]
        self.assertNotIn('Conditionnement vendu', text)


if __name__ == '__main__':
    unittest.main()
