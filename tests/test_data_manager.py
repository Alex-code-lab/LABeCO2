# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_data_manager.py
#
# Tests unitaires pour DataManager (méthodes sans I/O fichier).
# __init__ est contourné via __new__ pour éviter les dépendances HDF5.

import sys
import os
import unittest
from unittest.mock import MagicMock
import pandas as pd

# Neutraliser PySide6 et tables/HDF5
for _mod in ['PySide6', 'PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui', 'tables', 'tables.flavor']:
    sys.modules.setdefault(_mod, MagicMock())

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ui.data_manager import DataManager


def _make_dm():
    """DataManager sans I/O — contourne __init__."""
    dm = DataManager.__new__(DataManager)
    dm.CODE_NACRES_COL   = DataManager.CODE_NACRES_COL
    dm.CONSOMMABLE_COL   = DataManager.CONSOMMABLE_COL
    dm.MATERIAU_NAME_COL = DataManager.MATERIAU_NAME_COL
    dm.EQUIV_CO2_COL     = DataManager.EQUIV_CO2_COL
    dm.UNCERTAINTY_COL   = DataManager.UNCERTAINTY_COL
    dm.NOMBRE_PAR_COND_COL = DataManager.NOMBRE_PAR_COND_COL
    dm.PRIX_CONDITIONNEMENT_COL = DataManager.PRIX_CONDITIONNEMENT_COL
    dm.SOURCE_CATALOGUE_IJM_COL = DataManager.SOURCE_CATALOGUE_IJM_COL
    dm.UNITE_LIQUIDE_COL = DataManager.UNITE_LIQUIDE_COL
    dm.VOLUME_FLACON_COL = DataManager.VOLUME_FLACON_COL
    dm.FACTEUR_LIQUIDE_SOURCE_COL = DataManager.FACTEUR_LIQUIDE_SOURCE_COL
    dm.PRIX_UNITAIRE_COL = DataManager.PRIX_UNITAIRE_COL
    dm.PRIX_HT_COL       = DataManager.PRIX_HT_COL
    dm.CONDT_IJM_COL     = DataManager.CONDT_IJM_COL
    dm.NB_UNITES_IJM_COL = DataManager.NB_UNITES_IJM_COL
    dm.DESIGNATION_IJM_COL = DataManager.DESIGNATION_IJM_COL
    dm.CODE_IJM_COL      = DataManager.CODE_IJM_COL
    dm.MARQUE_IJM_COL    = DataManager.MARQUE_IJM_COL
    dm.SCORE_MATCH_COL   = DataManager.SCORE_MATCH_COL
    return dm


# ─────────────────────────────────────────────────────────────────────────────
# nacres_code_mask
# ─────────────────────────────────────────────────────────────────────────────

class TestNacresCodeMask(unittest.TestCase):

    def test_code_vide_retourne_tout_false(self):
        """Régression : code vide ne doit pas lever d'exception ni retourner True."""
        dm = _make_dm()
        series = pd.Series(["AA01", "NB13", "ZZ99"])
        mask = dm.nacres_code_mask(series, "")
        self.assertFalse(mask.any())
        self.assertEqual(len(mask), 3)

    def test_code_none_retourne_tout_false(self):
        dm = _make_dm()
        mask = dm.nacres_code_mask(pd.Series(["AA01", "NB13"]), None)
        self.assertFalse(mask.any())

    def test_correspondance_exacte(self):
        dm = _make_dm()
        series = pd.Series(["AA01", "NB13", "ZZ99"])
        mask = dm.nacres_code_mask(series, "NB13")
        self.assertEqual(list(mask), [False, True, False])

    def test_correspondance_prefixe_code_long(self):
        """'AA01 Tubes Eppendorf' doit matcher le code court 'AA01'."""
        dm = _make_dm()
        series = pd.Series(["AA01 Tubes Eppendorf", "NB13", "AA02"])
        mask = dm.nacres_code_mask(series, "AA01")
        self.assertTrue(mask.iloc[0])
        self.assertFalse(mask.iloc[1])
        self.assertFalse(mask.iloc[2])

    def test_insensible_a_la_casse(self):
        dm = _make_dm()
        series = pd.Series(["aa01", "NB13"])
        mask = dm.nacres_code_mask(series, "AA01")
        self.assertTrue(mask.iloc[0])

    def test_aucune_correspondance(self):
        dm = _make_dm()
        series = pd.Series(["AA01", "NB13"])
        mask = dm.nacres_code_mask(series, "ZZ99")
        self.assertFalse(mask.any())

    def test_serie_vide(self):
        dm = _make_dm()
        mask = dm.nacres_code_mask(pd.Series([], dtype=str), "AA01")
        self.assertEqual(len(mask), 0)

    def test_nan_dans_serie_ne_crash_pas(self):
        dm = _make_dm()
        series = pd.Series(["AA01", None, float("nan"), "NB13"])
        mask = dm.nacres_code_mask(series, "AA01")
        self.assertTrue(mask.iloc[0])
        self.assertFalse(mask.iloc[1])


# ─────────────────────────────────────────────────────────────────────────────
# get_liquid_data
# ─────────────────────────────────────────────────────────────────────────────

class TestGetLiquidData(unittest.TestCase):

    def _liquides_df(self):
        return pd.DataFrame([
            {"Code NACRES": "LA01", "Produit": "Éthanol",  "Densité (g/mL)": 0.789},
            {"Code NACRES": "LA02", "Produit": "Méthanol", "Densité (g/mL)": 0.791},
        ])

    def test_trouve_par_code(self):
        dm = _make_dm()
        dm.data_liquides = self._liquides_df()
        result = dm.get_liquid_data("LA01")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["Densité (g/mL)"], 0.789)

    def test_non_trouve_retourne_none(self):
        dm = _make_dm()
        dm.data_liquides = self._liquides_df()
        self.assertIsNone(dm.get_liquid_data("ZZ99"))

    def test_filtre_par_produit_correct(self):
        dm = _make_dm()
        dm.data_liquides = self._liquides_df()
        result = dm.get_liquid_data("LA01", produit="Éthanol")
        self.assertIsNotNone(result)

    def test_filtre_par_produit_incorrect(self):
        dm = _make_dm()
        dm.data_liquides = self._liquides_df()
        result = dm.get_liquid_data("LA01", produit="Méthanol")
        self.assertIsNone(result)

    def test_dataframe_vide_retourne_none(self):
        dm = _make_dm()
        dm.data_liquides = pd.DataFrame()
        self.assertIsNone(dm.get_liquid_data("LA01"))


# ─────────────────────────────────────────────────────────────────────────────
# get_material_data — intégration légère
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMaterialDataExtra(unittest.TestCase):
    """Cas supplémentaires non couverts dans test_carbon_calculator."""

    def _make_dm_with_mat(self, co2, uncert):
        dm = _make_dm()
        dm.data_materials = pd.DataFrame([{
            "Materiau": "Verre",
            "Equivalent CO₂ (kg eCO₂/kg)": co2,
            "uncertainty": uncert,
        }])
        return dm

    def test_retourne_valeurs_correctes(self):
        dm = self._make_dm_with_mat(1.2, 0.05)
        co2, unc = dm.get_material_data("Verre")
        self.assertAlmostEqual(co2, 1.2)
        self.assertAlmostEqual(unc, 0.05)

    def test_espaces_dans_nom_toleres(self):
        dm = self._make_dm_with_mat(1.2, 0.05)
        co2, unc = dm.get_material_data("  Verre  ")
        self.assertIsNotNone(co2)

    def test_materiau_inconnu_retourne_none(self):
        dm = self._make_dm_with_mat(1.2, 0.05)
        co2, unc = dm.get_material_data("Inconnu")
        self.assertIsNone(co2)
        self.assertIsNone(unc)


class TestPrixUnitaireCanonique(unittest.TestCase):

    def test_prix_unitaire_calcule_depuis_prix_conditionnement(self):
        dm = _make_dm()
        dm.data_masse = pd.DataFrame([{
            "Code NACRES": "NB11",
            "Consommable": "Tube IJM",
            "Prix du conditionnement": 70.0,
            "Nbr par conditionnement": 500,
            "Source catalogue IJM": "Catalogue IJM 2025",
            "condt_ijm": "1x500",
            "designation_ijm": "Tube IJM",
            "code_ijm": "P001",
            "marque_ijm": "MARQUE",
            "score_match": "",
        }])

        info = dm.get_prix_unitaire_info("NB11", "Tube IJM")

        self.assertIsNotNone(info)
        self.assertAlmostEqual(info["prix_unitaire"], 0.14)
        self.assertEqual(info["prix_ht"], 70.0)
        self.assertEqual(info["source_catalogue"], "Catalogue IJM 2025")

    def test_ligne_manuelle_exacte_sans_prix_ne_fuzzy_match_pas(self):
        dm = _make_dm()
        dm.data_masse = pd.DataFrame([
            {
                "Code NACRES": "NB11",
                "Consommable": "Tube manuel",
                "Prix du conditionnement": "",
                "Nbr par conditionnement": "",
            },
            {
                "Code NACRES": "NB11",
                "Consommable": "Tube catalogue",
                "Prix du conditionnement": 70.0,
                "Nbr par conditionnement": 500,
                "Source catalogue IJM": "Catalogue IJM 2025",
            },
        ])

        info = dm.get_prix_unitaire_info("NB11", "Tube manuel")

        self.assertIsNone(info)


# ─────────────────────────────────────────────────────────────────────────────
# is_liquid_commercial_row
# ─────────────────────────────────────────────────────────────────────────────

class TestIsLiquidCommercialRow(unittest.TestCase):

    def _row(self, facteur='', unite='', volume=0, code='', nom=''):
        return pd.Series({
            DataManager.CODE_NACRES_COL: code,
            DataManager.CONSOMMABLE_COL: nom,
            DataManager.FACTEUR_LIQUIDE_SOURCE_COL: facteur,
            DataManager.UNITE_LIQUIDE_COL:          unite,
            DataManager.VOLUME_FLACON_COL:          volume,
        })

    def test_none_retourne_false(self):
        dm = _make_dm()
        self.assertFalse(dm.is_liquid_commercial_row(None))

    def test_volume_positif_seul_retourne_false(self):
        dm = _make_dm()
        self.assertFalse(dm.is_liquid_commercial_row(self._row(volume=500)))

    def test_volume_positif_code_na_retourne_true(self):
        dm = _make_dm()
        self.assertTrue(dm.is_liquid_commercial_row(
            self._row(unite='mL', volume=500, code='NA21', nom='Solution test 500ml')
        ))

    def test_objet_solide_avec_capacite_retourne_false(self):
        dm = _make_dm()
        self.assertFalse(dm.is_liquid_commercial_row(
            self._row(unite='mL', volume=300, code='HA11', nom='BOITE à DÉCHETS 300ml')
        ))

    def test_volume_zero_retourne_false(self):
        """Régression : Volume flacon = 0 ne doit pas classifier comme liquide."""
        dm = _make_dm()
        self.assertFalse(dm.is_liquid_commercial_row(self._row(volume=0)))

    def test_volume_zero_float_retourne_false(self):
        dm = _make_dm()
        self.assertFalse(dm.is_liquid_commercial_row(self._row(volume=0.0)))

    def test_facteur_renseigne_retourne_true(self):
        dm = _make_dm()
        self.assertTrue(dm.is_liquid_commercial_row(self._row(facteur='Éthanol')))

    def test_unite_renseignee_retourne_true(self):
        dm = _make_dm()
        self.assertTrue(dm.is_liquid_commercial_row(
            self._row(unite='mL', code='NB22', nom='Acrylamide solution 500ml')
        ))

    def test_tous_vides_retourne_false(self):
        dm = _make_dm()
        self.assertFalse(dm.is_liquid_commercial_row(self._row()))


# ─────────────────────────────────────────────────────────────────────────────
# get_consumable_liquid_factor_data
# ─────────────────────────────────────────────────────────────────────────────

class TestGetConsumableLiquidFactorData(unittest.TestCase):

    def _masse_df(self, code='NA02', nom='Acétone 1L', facteur='Acétone',
                  unite='mL', volume=1000):
        return pd.DataFrame([{
            DataManager.CODE_NACRES_COL:            code,
            DataManager.CONSOMMABLE_COL:            nom,
            DataManager.FACTEUR_LIQUIDE_SOURCE_COL: facteur,
            DataManager.UNITE_LIQUIDE_COL:          unite,
            DataManager.VOLUME_FLACON_COL:          volume,
        }])

    def _liquides_df(self, code='NA02', produit='Acétone'):
        return pd.DataFrame([{
            DataManager.CODE_NACRES_COL: code,
            'Produit':                   produit,
            'Facteur CO₂ (kg CO₂e/kg)': 2.1,
        }])

    def test_produit_absent_retourne_none_none(self):
        dm = _make_dm()
        dm.data_masse   = pd.DataFrame(columns=[
            DataManager.CODE_NACRES_COL, DataManager.CONSOMMABLE_COL,
            DataManager.FACTEUR_LIQUIDE_SOURCE_COL,
        ])
        dm.data_liquides = pd.DataFrame()
        product_row, factor_row = dm.get_consumable_liquid_factor_data('ZZ99', 'Inconnu')
        self.assertIsNone(product_row)
        self.assertIsNone(factor_row)

    def test_pas_de_facteur_source_retourne_row_et_none(self):
        """Produit trouvé mais sans Facteur liquide source → (product_row, None)."""
        dm = _make_dm()
        dm.data_masse = self._masse_df(facteur='')
        dm.data_liquides = pd.DataFrame()
        product_row, factor_row = dm.get_consumable_liquid_factor_data('NA02', 'Acétone 1L')
        self.assertIsNotNone(product_row)
        self.assertIsNone(factor_row)

    def test_facteur_trouve_retourne_les_deux(self):
        dm = _make_dm()
        dm.data_masse   = self._masse_df()
        dm.data_liquides = self._liquides_df()
        product_row, factor_row = dm.get_consumable_liquid_factor_data('NA02', 'Acétone 1L')
        self.assertIsNotNone(product_row)
        self.assertIsNotNone(factor_row)
        self.assertEqual(str(factor_row['Produit']), 'Acétone')

    def test_facteur_absent_de_data_liquides_retourne_none(self):
        """Facteur source renseigné mais absent de data_liquides → (product_row, None)."""
        dm = _make_dm()
        dm.data_masse   = self._masse_df(facteur='SolvantInconnu')
        dm.data_liquides = self._liquides_df(produit='Acétone')  # 'SolvantInconnu' absent
        product_row, factor_row = dm.get_consumable_liquid_factor_data('NA02', 'Acétone 1L')
        self.assertIsNotNone(product_row)
        self.assertIsNone(factor_row)


if __name__ == "__main__":
    unittest.main()
