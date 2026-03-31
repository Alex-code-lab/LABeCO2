# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_carbon_calculator.py
#
# Tests unitaires pour CarbonCalculator.
# Le DataManager est mocké : aucun fichier HDF5 ni UI nécessaire.

import math
import sys
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

# ── Neutraliser PySide6 et tables/HDF5 pour les tests (pas d'écran requis) ───
for _mod in [
    'PySide6', 'PySide6.QtWidgets', 'PySide6.QtGui', 'PySide6.QtCore',
    'PySide6.QtCharts', 'PySide6.QtPrintSupport',
    'tables', 'tables.flavor',
]:
    sys.modules.setdefault(_mod, MagicMock())

# ── Ajouter la racine du projet au path ──────────────────────────────────────
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from windows.carbon_calculator import CarbonCalculator


# ── Fabrique de DataManager mocké ────────────────────────────────────────────

def _make_dm(
    main_data=None,
    data_masse=None,
    data_materials=None,
    material_map=None,     # {nom: (co2_par_kg, incert)} ou None → (None, None)
    liquid_row=None,       # Series ou None
):
    """
    Retourne un DataManager factice paramétrable.
    """
    dm = MagicMock()

    # Base de données GES principale
    if main_data is None:
        main_data = pd.DataFrame({
            'category':        ['Achats', 'Véhicules'],
            'subcategory':     ['Consommables de laboratoire', 'Voiture'],
            'subsubcategory':  ['AA01', ''],
            'name':            ['Réactifs', 'Voiture essence'],
            'year':            ['', ''],
            'total':           [0.5, 0.25],
            'uncertainty':     [0.1, 0.05],
            'unit':            ['€', 'km'],
        })
    dm.get_main_data.return_value = main_data

    # Consommables solides
    if data_masse is None:
        data_masse = pd.DataFrame(columns=[
            'Code NACRES', 'Consommable',
            'Masse unitaire (g)', 'Matériau consommable',
            'Masse unitaire deuxieme materiaux (g)', 'Matériau deuxieme materiaux',
            'Masse emballage unitaire (g)', 'Matériau emballage',
            'Masse condionnement (g)', 'Matériau conditionnement',
            'Nbr par conditionnement',
        ])
    dm.get_data_masse.return_value = data_masse

    # Constantes de colonnes (copiées de DataManager)
    dm.CODE_NACRES_COL            = 'Code NACRES'
    dm.CONSOMMABLE_COL            = 'Consommable'
    dm.MASSE_G_COL                = 'Masse unitaire (g)'
    dm.MATERIAU_COL               = 'Matériau consommable'
    dm.MASSE_G2_COL               = 'Masse unitaire deuxieme materiaux (g)'
    dm.MATERIAU2_COL              = 'Matériau deuxieme materiaux'
    dm.MASSE_EMBALLAGE_COL        = 'Masse emballage unitaire (g)'
    dm.MATERIAU_EMBALLAGE_COL     = 'Matériau emballage'
    dm.MASSE_CONDITIONNEMENT_COL  = 'Masse condionnement (g)'
    dm.MATERIAU_CONDITIONNEMENT_COL = 'Matériau conditionnement'
    dm.NOMBRE_PAR_COND_COL        = 'Nbr par conditionnement'

    # Matériaux
    if material_map is not None:
        def _get_material(name):
            return material_map.get(name, (None, None))
        dm.get_material_data.side_effect = _get_material
    else:
        dm.get_material_data.return_value = (None, None)

    # Liquides
    dm.get_liquid_data.return_value = liquid_row

    return dm


# ─────────────────────────────────────────────────────────────────────────────
# 1. Calcul Machine
# ─────────────────────────────────────────────────────────────────────────────

class TestMachine(unittest.TestCase):

    def _make_main_data_elec(self, factor=0.4, uncert=0.1):
        return pd.DataFrame({
            'category':    ['Électricité'],
            'subcategory': [''],
            'name':        ['Réseau France'],
            'total':       [factor],
            'uncertainty': [uncert],
        })

    def test_machine_calcul_nominal(self):
        """kWh × facteur = émissions correctes."""
        dm = _make_dm(main_data=self._make_main_data_elec(factor=0.4, uncert=0.1))
        calc = CarbonCalculator(dm)
        # val = 10 kWh déjà calculés en amont
        result = calc.compute_emission_data({
            'category': 'Machine',
            'electricity_type': 'Réseau France',
            'value': 10.0,
        })
        ep, ep_err, em, em_err, tm, msg = result
        self.assertAlmostEqual(ep, 4.0)          # 10 × 0.4
        self.assertAlmostEqual(ep_err, 0.4)      # 4.0 × 0.1
        self.assertEqual(em, 0.0)
        self.assertIsNone(msg)

    def test_machine_type_elec_inconnu(self):
        """Facteur introuvable → message d'erreur, résultat nul."""
        dm = _make_dm(main_data=self._make_main_data_elec())
        calc = CarbonCalculator(dm)
        ep, ep_err, em, em_err, tm, msg = calc.compute_emission_data({
            'category': 'Machine',
            'electricity_type': 'Énergie inconnue',
            'value': 10.0,
        })
        self.assertEqual(ep, 0.0)
        self.assertIsNotNone(msg)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Calcul Véhicules
# ─────────────────────────────────────────────────────────────────────────────

class TestVehicules(unittest.TestCase):

    def _main_data_vehicule(self, factor=0.25):
        return pd.DataFrame({
            'category':        ['Véhicules'],
            'subcategory':     ['Voiture'],
            'subsubcategory':  [''],
            'name':            ['Voiture essence'],
            'year':            [''],
            'total':           [factor],
            'uncertainty':     [0.0],
            'unit':            ['km'],
        })

    def test_vehicule_multiplie_par_days(self):
        """val (km/jour) × days doit être multiplié dans le calcul."""
        dm = _make_dm(main_data=self._main_data_vehicule(factor=0.25))
        calc = CarbonCalculator(dm)
        ep, *_, msg = calc.compute_emission_data({
            'category': 'Véhicules',
            'subcategory': 'Voiture',
            'subsubcategory': '',
            'name': 'Voiture essence',
            'year': '',
            'value': 100.0,   # 100 km/jour
            'days': 5,
            'code_nacres': 'NA',
        })
        # total_value = 100 × 5 = 500 km ; ep = 500 × 0.25 = 125
        self.assertAlmostEqual(ep, 125.0)
        self.assertIsNone(msg)

    def test_vehicule_valeur_stockee_est_km_par_jour(self):
        """Après édition, 'value' doit rester km/jour (pas km total)."""
        dm = _make_dm(main_data=self._main_data_vehicule(factor=0.25))
        calc = CarbonCalculator(dm)
        # Simule un double calcul (saisie puis réédition sans modification)
        data = {
            'category': 'Véhicules',
            'subcategory': 'Voiture',
            'subsubcategory': '',
            'name': 'Voiture essence',
            'year': '',
            'value': 100.0,
            'days': 5,
            'code_nacres': 'NA',
        }
        ep1, *_ = calc.compute_emission_data(data)
        ep2, *_ = calc.compute_emission_data(data)
        self.assertAlmostEqual(ep1, ep2, msg="Résultat doit être idempotent")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Calcul masse consommables solides
# ─────────────────────────────────────────────────────────────────────────────

class TestMassBasedEmissions(unittest.TestCase):

    def _make_data_masse(self, masse_g=50.0, materiau='Plastique', masse_emb=10.0, mat_emb='Carton'):
        return pd.DataFrame([{
            'Code NACRES': 'AA01',
            'Consommable': 'Tube Eppendorf',
            'Masse unitaire (g)': masse_g,
            'Matériau consommable': materiau,
            'Masse unitaire deuxieme materiaux (g)': 0.0,
            'Matériau deuxieme materiaux': '',
            'Masse emballage unitaire (g)': masse_emb,
            'Matériau emballage': mat_emb,
            'Masse condionnement (g)': 0.0,
            'Matériau conditionnement': '',
            'Nbr par conditionnement': 1,
        }])

    def test_calcul_nominal_deux_materiaux(self):
        """Produit + emballage → somme des émissions."""
        dm = _make_dm(
            data_masse=self._make_data_masse(masse_g=50.0, materiau='Plastique',
                                              masse_emb=10.0, mat_emb='Carton'),
            material_map={
                'Plastique': (2.0, 0.1),  # 2 kgCO2/kg, 10% incert
                'Carton':    (1.0, 0.05),
            }
        )
        calc = CarbonCalculator(dm)
        emission, masse, unc, missing = calc._calculate_mass_based_emissions_old(
            'AA01', 'Tube Eppendorf', quantity=10
        )
        # masse_plastique = 10 × 50/1000 = 0.5 kg → 0.5×2 = 1.0 kgCO2
        # masse_carton    = 10 × 10/1000 = 0.1 kg → 0.1×1 = 0.1 kgCO2
        self.assertAlmostEqual(emission, 1.1)
        self.assertAlmostEqual(masse, 0.6)
        self.assertEqual(missing, [])

    def test_materiau_manquant_signale_et_non_comptabilise(self):
        """Matériau absent → apparaît dans missing, masse NON comptée."""
        dm = _make_dm(
            data_masse=self._make_data_masse(masse_g=50.0, materiau='MatériauInconnu',
                                              masse_emb=10.0, mat_emb='Carton'),
            material_map={
                'Carton': (1.0, 0.0),
                # 'MatériauInconnu' absent intentionnellement
            }
        )
        calc = CarbonCalculator(dm)
        emission, masse, unc, missing = calc._calculate_mass_based_emissions_old(
            'AA01', 'Tube Eppendorf', quantity=10
        )
        # Seul Carton contribue
        self.assertAlmostEqual(emission, 0.1)      # 10×10/1000×1.0
        self.assertAlmostEqual(masse, 0.1)         # masse du plastique ignorée
        self.assertIn('MatériauInconnu', missing)

    def test_materiau_manquant_masse_non_comptee(self):
        """Régression bug #1 : la masse du composant inconnu ne doit pas être dans le total."""
        dm = _make_dm(
            data_masse=self._make_data_masse(masse_g=500.0, materiau='Inconnu',
                                              masse_emb=0.0, mat_emb=''),
            material_map={}  # aucun matériau connu
        )
        calc = CarbonCalculator(dm)
        _, masse, _, missing = calc._calculate_mass_based_emissions_old(
            'AA01', 'Tube Eppendorf', quantity=1
        )
        self.assertEqual(masse, 0.0, "La masse ne doit pas être comptée si le matériau est inconnu")
        self.assertIn('Inconnu', missing)

    def test_nan_dans_masse_traite_comme_zero(self):
        """Régression bug NaN : une masse NaN ne doit pas propager NaN."""
        df = pd.DataFrame([{
            'Code NACRES': 'AA01',
            'Consommable': 'Tube Eppendorf',
            'Masse unitaire (g)': float('nan'),
            'Matériau consommable': 'Plastique',
            'Masse unitaire deuxieme materiaux (g)': float('nan'),
            'Matériau deuxieme materiaux': '',
            'Masse emballage unitaire (g)': 10.0,
            'Matériau emballage': 'Carton',
            'Masse condionnement (g)': float('nan'),
            'Matériau conditionnement': '',
            'Nbr par conditionnement': 1,
        }])
        dm = _make_dm(
            data_masse=df,
            material_map={'Plastique': (2.0, 0.1), 'Carton': (1.0, 0.0)}
        )
        calc = CarbonCalculator(dm)
        emission, masse, unc, missing = calc._calculate_mass_based_emissions_old(
            'AA01', 'Tube Eppendorf', quantity=5
        )
        self.assertFalse(math.isnan(emission), "emission ne doit pas être NaN")
        self.assertFalse(math.isnan(masse),    "masse ne doit pas être NaN")
        self.assertEqual(missing, [])

    def test_code_nacres_na_retourne_zero(self):
        """Code NACRES 'NA' → résultat nul sans erreur."""
        dm = _make_dm()
        calc = CarbonCalculator(dm)
        emission, masse, unc, missing = calc._calculate_mass_based_emissions_old('NA', 'x', 1)
        self.assertEqual(emission, 0.0)
        self.assertEqual(masse, 0.0)
        self.assertEqual(missing, [])

    def test_consommable_introuvable_retourne_zero(self):
        """Consommable absent de data_masse → résultat nul."""
        dm = _make_dm(data_masse=self._make_data_masse())
        calc = CarbonCalculator(dm)
        emission, masse, unc, missing = calc._calculate_mass_based_emissions_old(
            'ZZ99', 'Inconnu', quantity=5
        )
        self.assertEqual(emission, 0.0)
        self.assertEqual(missing, [])


# ─────────────────────────────────────────────────────────────────────────────
# 4. Calcul liquides
# ─────────────────────────────────────────────────────────────────────────────

class TestLiquidEmissions(unittest.TestCase):

    def test_calcul_nominal_liquide(self):
        """volume (mL) × densité × facteur CO2 → émissions."""
        liquid_row = pd.Series({
            'Code NACRES': 'LA01',
            'Densité (g/mL)': 0.8,
            'Facteur CO₂ (kg CO₂e/kg)': 3.0,
            'Incertitude (%)': 10.0,
        })
        dm = _make_dm(liquid_row=liquid_row)
        calc = CarbonCalculator(dm)
        emission, masse, err = calc._calculate_liquid_emissions('LA01', volume_ml=500)
        # masse = 0.8 × 500 / 1000 = 0.4 kg
        # emission = 0.4 × 3.0 = 1.2 kgCO2
        self.assertAlmostEqual(masse, 0.4)
        self.assertAlmostEqual(emission, 1.2)
        self.assertAlmostEqual(err, 0.12)  # 1.2 × 10%

    def test_liquide_introuvable_retourne_zero(self):
        """Code NACRES absent → résultat nul."""
        dm = _make_dm(liquid_row=None)
        calc = CarbonCalculator(dm)
        emission, masse, err = calc._calculate_liquid_emissions('ZZ99', volume_ml=100)
        self.assertEqual(emission, 0.0)
        self.assertEqual(masse, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 5. get_material_data — gestion des NaN
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMaterialData(unittest.TestCase):
    """Tests directs sur DataManager.get_material_data (pas de mock)."""

    def _make_real_dm(self, co2_value, uncert_value):
        """Crée un DataManager minimal avec data_materials injectée à la main."""
        from windows.data_manager import DataManager
        dm = DataManager.__new__(DataManager)
        dm.data_materials = pd.DataFrame([{
            'Materiau': 'Plastique',
            'Equivalent CO₂ (kg eCO₂/kg)': co2_value,
            'uncertainty': uncert_value,
        }])
        dm.MATERIAU_NAME_COL = 'Materiau'
        dm.EQUIV_CO2_COL     = 'Equivalent CO₂ (kg eCO₂/kg)'
        dm.UNCERTAINTY_COL   = 'uncertainty'
        return dm

    def test_valeur_normale(self):
        dm = self._make_real_dm(co2_value=2.5, uncert_value=0.1)
        co2, unc = dm.get_material_data('Plastique')
        self.assertAlmostEqual(co2, 2.5)
        self.assertAlmostEqual(unc, 0.1)

    def test_co2_nan_retourne_zero(self):
        """Régression : NaN dans la colonne CO2 → 0.0, pas NaN."""
        dm = self._make_real_dm(co2_value=float('nan'), uncert_value=0.1)
        co2, unc = dm.get_material_data('Plastique')
        self.assertFalse(math.isnan(co2), "co2 ne doit pas être NaN")
        self.assertEqual(co2, 0.0)

    def test_incert_nan_retourne_zero(self):
        """Régression : NaN dans l'incertitude → 0.0, pas NaN."""
        dm = self._make_real_dm(co2_value=2.5, uncert_value=float('nan'))
        co2, unc = dm.get_material_data('Plastique')
        self.assertFalse(math.isnan(unc), "incertitude ne doit pas être NaN")
        self.assertEqual(unc, 0.0)

    def test_materiau_inconnu_retourne_none(self):
        dm = self._make_real_dm(co2_value=2.5, uncert_value=0.1)
        co2, unc = dm.get_material_data('MatériauInexistant')
        self.assertIsNone(co2)
        self.assertIsNone(unc)

    def test_materiau_nan_retourne_none(self):
        dm = self._make_real_dm(co2_value=2.5, uncert_value=0.1)
        co2, unc = dm.get_material_data(float('nan'))
        self.assertIsNone(co2)

    def test_materiau_non_string_retourne_none(self):
        dm = self._make_real_dm(co2_value=2.5, uncert_value=0.1)
        co2, unc = dm.get_material_data(42)
        self.assertIsNone(co2)


if __name__ == '__main__':
    unittest.main()
