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

from ui.carbon_calculator import CarbonCalculator


# ── Fabrique de DataManager mocké ────────────────────────────────────────────

def _make_dm(
    main_data=None,
    data_masse=None,
    data_materials=None,
    material_map=None,     # {nom: (co2_par_kg, incert)} ou None → (None, None)
    liquid_row=None,       # Series ou None
    eol_material_map=None, # {nom: (co2_eol, incert_eol, factor_name)} pour les emballages
    filiere_map=None,      # {prefixe_nacres: (co2_filiere, incert, filiere_name)}
):
    """
    Retourne un DataManager factice paramétrable.

    Par défaut, les méthodes EoL renvoient des valeurs neutres (pas de contribution
    fin de vie) pour que les tests historiques continuent de passer sans surprise.
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
    dm.CONDT_IJM_COL              = 'condt_ijm'
    dm.MASSE_G3_COL               = 'Masse unitaire troisième materiaux (g)'
    dm.MATERIAU3_COL              = 'Matériau troisième materiaux'

    def _nacres_code_mask(series, code_nacres):
        code = str(code_nacres or '').strip().upper()
        prefix = code[:4]
        clean = series.fillna('').astype(str).str.strip().str.upper()
        return (clean == code) | (clean.str[:4] == prefix)
    dm.nacres_code_mask.side_effect = _nacres_code_mask

    # Matériaux
    if material_map is not None:
        def _get_material(name):
            return material_map.get(name, (None, None))
        dm.get_material_data.side_effect = _get_material
    else:
        dm.get_material_data.return_value = (None, None)

    # EoL — par matériau (emballages / conditionnement)
    if eol_material_map is not None:
        def _get_eol(name):
            return eol_material_map.get(name, (None, None, None))
        dm.get_material_eol_data.side_effect = _get_eol
    else:
        dm.get_material_eol_data.return_value = (None, None, None)

    # EoL — filière par NACRES (consommable contaminé : DASRI / DIS)
    if filiere_map is not None:
        def _get_filiere(code):
            prefix = (code or "")[:2].upper()
            return filiere_map.get(prefix, (None, None, "DASRI"))
        dm.get_filiere_factor.side_effect = _get_filiere
    else:
        dm.get_filiere_factor.return_value = (None, None, "DASRI")

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

    def test_chaine_vide_dans_masse_traitee_comme_zero(self):
        """Régression UI : une masse vide '' ne doit pas faire planter float('')."""
        df = pd.DataFrame([{
            'Code NACRES': 'AA01',
            'Consommable': 'Agar catalogue',
            'Masse unitaire (g)': '',
            'Matériau consommable': 'Plastique',
            'Masse unitaire deuxieme materiaux (g)': '',
            'Matériau deuxieme materiaux': '',
            'Masse unitaire troisième materiaux (g)': '',
            'Matériau troisième materiaux': '',
            'Masse emballage unitaire (g)': '',
            'Matériau emballage': '',
            'Masse condionnement (g)': '',
            'Matériau conditionnement': '',
            'Nbr par conditionnement': '',
        }])
        dm = _make_dm(
            data_masse=df,
            material_map={'Plastique': (2.0, 0.1)}
        )
        calc = CarbonCalculator(dm)
        emission, masse, unc, missing = calc._calculate_mass_based_emissions_old(
            'AA01', 'Agar catalogue', quantity=5
        )
        self.assertEqual(emission, 0.0)
        self.assertEqual(masse, 0.0)
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

    def test_emballage_secondaire_divisé_par_nbr_unites(self):
        """Masse d'emballage secondaire / Nbr par emballage secondaire si > 1.

        Cas : sachet plastique de 50 g qui regroupe 50 tubes → 1 g/tube imputé.
        """
        df = pd.DataFrame([{
            'Code NACRES': 'AA01',
            'Consommable': 'Tube bulk',
            'Masse unitaire (g)': 6.7,
            'Matériau consommable': 'Plastique',
            'Masse unitaire deuxieme materiaux (g)': 0.0,
            'Matériau deuxieme materiaux': '',
            'Masse emballage unitaire (g)': 50.0,
            'Matériau emballage': 'Carton',
            'Nbr par emballage secondaire': 50,
            'Masse condionnement (g)': 0.0,
            'Matériau conditionnement': '',
            'Nbr par conditionnement': 1,
        }])
        dm = _make_dm(
            data_masse=df,
            material_map={'Plastique': (2.0, 0.0), 'Carton': (1.0, 0.0)},
        )
        dm.NOMBRE_PAR_EMBALLAGE_COL = 'Nbr par emballage secondaire'
        calc = CarbonCalculator(dm)
        emission, masse, _, _ = calc._calculate_mass_based_emissions_old(
            'AA01', 'Tube bulk', quantity=3
        )
        # plastique = 3 × 6.7/1000 × 2.0 = 0.0402
        # carton    = 3 × (50/50)/1000 × 1.0 = 0.003   (1 g par tube)
        self.assertAlmostEqual(emission, 0.0402 + 0.003)
        self.assertAlmostEqual(masse, 3 * 6.7 / 1000 + 3 * 1.0 / 1000)

    def test_emballage_secondaire_diviseur_vide_equivaut_un(self):
        """Diviseur vide ou absent → comportement legacy (masse déjà par unité)."""
        df = pd.DataFrame([{
            'Code NACRES': 'AA01',
            'Consommable': 'Tube wrappé',
            'Masse unitaire (g)': 6.7,
            'Matériau consommable': 'Plastique',
            'Masse unitaire deuxieme materiaux (g)': 0.0,
            'Matériau deuxieme materiaux': '',
            'Masse emballage unitaire (g)': 2.0,
            'Matériau emballage': 'Carton',
            'Nbr par emballage secondaire': '',  # vide = pas de mutualisation
            'Masse condionnement (g)': 0.0,
            'Matériau conditionnement': '',
            'Nbr par conditionnement': 1,
        }])
        dm = _make_dm(
            data_masse=df,
            material_map={'Plastique': (2.0, 0.0), 'Carton': (1.0, 0.0)},
        )
        dm.NOMBRE_PAR_EMBALLAGE_COL = 'Nbr par emballage secondaire'
        calc = CarbonCalculator(dm)
        emission, _, _, _ = calc._calculate_mass_based_emissions_old(
            'AA01', 'Tube wrappé', quantity=1
        )
        # 1 × 6.7/1000 × 2.0 + 1 × 2.0/1000 × 1.0 = 0.0134 + 0.002
        self.assertAlmostEqual(emission, 0.0134 + 0.002)

    def test_conditionnement_choisit_la_bonne_ligne(self):
        """Deux consommables de même nom doivent rester distingués par conditionnement."""
        df = pd.DataFrame([
            {
                'Code NACRES': 'NA25',
                'Consommable': 'Talc',
                'Masse unitaire (g)': 1000.0,
                'Matériau consommable': 'Matériau 1 kg',
                'Masse unitaire deuxieme materiaux (g)': 0.0,
                'Matériau deuxieme materiaux': '',
                'Masse emballage unitaire (g)': 0.0,
                'Matériau emballage': '',
                'Masse condionnement (g)': 0.0,
                'Matériau conditionnement': '',
                'Nbr par conditionnement': 1,
                'condt_ijm': '1 kg',
            },
            {
                'Code NACRES': 'NA25',
                'Consommable': 'Talc',
                'Masse unitaire (g)': 5000.0,
                'Matériau consommable': 'Matériau 5 kg',
                'Masse unitaire deuxieme materiaux (g)': 0.0,
                'Matériau deuxieme materiaux': '',
                'Masse emballage unitaire (g)': 0.0,
                'Matériau emballage': '',
                'Masse condionnement (g)': 0.0,
                'Matériau conditionnement': '',
                'Nbr par conditionnement': 1,
                'condt_ijm': '5 kg',
            },
        ])
        dm = _make_dm(
            data_masse=df,
            material_map={
                'Matériau 1 kg': (1.0, 0.0),
                'Matériau 5 kg': (2.0, 0.0),
            },
        )
        calc = CarbonCalculator(dm)

        emission, masse, unc, missing = calc._calculate_mass_based_emissions_old(
            'NA25', 'Talc', quantity=1, packaging='5 kg'
        )

        self.assertAlmostEqual(masse, 5.0)
        self.assertAlmostEqual(emission, 10.0)
        self.assertEqual(missing, [])


# ─────────────────────────────────────────────────────────────────────────────
# 3-bis. Calcul fin de vie (incinération)
# ─────────────────────────────────────────────────────────────────────────────

class TestEndOfLifeEmissions(unittest.TestCase):
    """Vérifie que la fin de vie est correctement ajoutée au total :
    - consommable → filière DASRI/DIS uniforme (routage NACRES)
    - emballage / conditionnement → facteur EoL par matériau
    - matériaux sans mapping EoL → ignorés silencieusement (métaux)
    """

    @staticmethod
    def _make_data_masse(masse_g=10.0, materiau='Polypropylène (PP)',
                         masse_emb=0.0, mat_emb='', code_nacres='NB11'):
        return pd.DataFrame([{
            'Code NACRES': code_nacres,
            'Consommable': 'Tube',
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

    def test_consommable_dasri_ajoute_au_total(self):
        """NACRES NB → filière DASRI : émission EoL = masse × 0.943 ajoutée à la production."""
        dm = _make_dm(
            data_masse=self._make_data_masse(masse_g=10.0, materiau='PP'),
            material_map={'PP': (3.0, 0.0)},
            filiere_map={'NB': (0.943, 0.50, 'DASRI')},
        )
        calc = CarbonCalculator(dm)
        emission, masse, unc, missing = calc._calculate_mass_based_emissions_old(
            'NB11', 'Tube', quantity=100,
        )
        # 100 × 10/1000 = 1 kg ; production = 1×3.0 = 3.0 ; EoL DASRI = 1×0.943 = 0.943
        self.assertAlmostEqual(masse, 1.0)
        self.assertAlmostEqual(emission, 3.0 + 0.943, places=4)
        self.assertEqual(missing, [])

    def test_consommable_dis_pour_solvant(self):
        """NACRES NA (chimie) → filière DIS : facteur 0.844 au lieu de DASRI."""
        dm = _make_dm(
            data_masse=self._make_data_masse(masse_g=10.0, materiau='PP', code_nacres='NA02'),
            material_map={'PP': (3.0, 0.0)},
            filiere_map={'NA': (0.844, 0.20, 'DIS')},
        )
        calc = CarbonCalculator(dm)
        emission, masse, _, _ = calc._calculate_mass_based_emissions_old(
            'NA02', 'Tube', quantity=100,
        )
        self.assertAlmostEqual(emission, 3.0 + 0.844, places=4)
        self.assertAlmostEqual(masse, 1.0)

    def test_emballage_route_par_materiau(self):
        """Emballage carton → facteur EoL carton (0.120), PAS la filière du consommable."""
        dm = _make_dm(
            data_masse=self._make_data_masse(
                masse_g=10.0, materiau='PP',
                masse_emb=5.0, mat_emb='Carton',
            ),
            material_map={'PP': (3.0, 0.0), 'Carton': (1.0, 0.0)},
            eol_material_map={'Carton': (0.120, 0.20, 'Emballages/Carton')},
            filiere_map={'NB': (0.943, 0.50, 'DASRI')},
        )
        calc = CarbonCalculator(dm)
        emission, masse, _, _ = calc._calculate_mass_based_emissions_old(
            'NB11', 'Tube', quantity=100,
        )
        # PP : prod 1×3.0 + EoL DASRI 1×0.943 = 3.943
        # Carton : prod 0.5×1.0 + EoL 0.5×0.120 = 0.560
        # Total : 4.503
        self.assertAlmostEqual(masse, 1.5)
        self.assertAlmostEqual(emission, 3.943 + 0.560, places=4)

    def test_metal_sans_eol_pas_de_contribution(self):
        """Matériau sans facteur EoL (métal) → contribution EoL ignorée silencieusement."""
        dm = _make_dm(
            data_masse=self._make_data_masse(
                masse_g=10.0, materiau='PP',
                masse_emb=5.0, mat_emb='Aluminium',
            ),
            material_map={'PP': (3.0, 0.0), 'Aluminium': (11.0, 0.0)},
            eol_material_map={
                # Aluminium volontairement absent : pas de mapping EoL.
                # On définit seulement PP pour vérifier qu'il n'est pas pris
                # pour l'emballage Aluminium (qui doit rester sans EoL).
            },
            filiere_map={'NB': (0.943, 0.50, 'DASRI')},
        )
        calc = CarbonCalculator(dm)
        emission, masse, _, missing = calc._calculate_mass_based_emissions_old(
            'NB11', 'Tube', quantity=100,
        )
        # PP : prod 1×3.0 + EoL DASRI 1×0.943 = 3.943
        # Alu : prod 0.5×11.0 = 5.5 (pas d'EoL)
        # Total : 9.443
        self.assertAlmostEqual(masse, 1.5)
        self.assertAlmostEqual(emission, 3.943 + 5.5, places=4)
        self.assertEqual(missing, [])

    def test_sans_eol_configure_retrocompatible(self):
        """Si aucun facteur filière ni EoL matériau n'est dispo → comportement v2 inchangé."""
        dm = _make_dm(
            data_masse=self._make_data_masse(masse_g=10.0, materiau='PP'),
            material_map={'PP': (3.0, 0.0)},
            # Pas de filiere_map ni eol_material_map → None partout
        )
        calc = CarbonCalculator(dm)
        emission, masse, _, _ = calc._calculate_mass_based_emissions_old(
            'NB11', 'Tube', quantity=100,
        )
        # Seule la production compte
        self.assertAlmostEqual(emission, 3.0, places=4)
        self.assertAlmostEqual(masse, 1.0)

    def test_breakdown_disponible_apres_calcul(self):
        """Le calcul masse-based remplit calc.last_breakdown avec le détail par composant."""
        dm = _make_dm(
            data_masse=self._make_data_masse(
                masse_g=10.0, materiau='PP',
                masse_emb=5.0, mat_emb='Carton',
            ),
            material_map={'PP': (3.0, 0.0), 'Carton': (1.0, 0.0)},
            eol_material_map={'Carton': (0.120, 0.20, 'Emballages/Carton')},
            filiere_map={'NB': (0.943, 0.50, 'DASRI')},
        )
        calc = CarbonCalculator(dm)
        calc._calculate_mass_based_emissions_old('NB11', 'Tube', quantity=100)

        bd = calc.last_breakdown
        self.assertIsNotNone(bd)
        self.assertEqual(bd['filiere_consommable'], 'DASRI')
        # 2 composants traités : PP (product) + Carton (packaging)
        comps_traites = [c for c in bd['components']]
        self.assertEqual(len(comps_traites), 2)

        # Composant PP : production + EoL DASRI
        pp = comps_traites[0]
        self.assertEqual(pp['type'], 'product')
        self.assertEqual(pp['material'], 'PP')
        self.assertAlmostEqual(pp['mass_kg_total'], 1.0)
        self.assertAlmostEqual(pp['production']['co2'], 3.0)
        self.assertEqual(pp['eol']['filiere'], 'DASRI')
        self.assertAlmostEqual(pp['eol']['co2'], 0.943)
        self.assertFalse(pp['eol']['missing'])

        # Composant Carton : production + EoL par matériau
        carton = comps_traites[1]
        self.assertEqual(carton['type'], 'packaging')
        self.assertIsNone(carton['eol']['filiere'])
        self.assertAlmostEqual(carton['eol']['co2'], 0.5 * 0.120)

        # Agrégats
        totals = bd['totals']
        self.assertAlmostEqual(totals['production'], 3.0 + 0.5)         # 3.5
        self.assertAlmostEqual(totals['eol_consommable'], 0.943)
        self.assertAlmostEqual(totals['eol_packaging'], 0.060)
        self.assertAlmostEqual(totals['total'], 3.5 + 0.943 + 0.060)

    def test_breakdown_signale_materiau_sans_eol(self):
        """Un emballage en métal (sans EoL) apparaît dans missing_eol et eol.missing=True."""
        dm = _make_dm(
            data_masse=self._make_data_masse(
                masse_g=10.0, materiau='PP',
                masse_emb=5.0, mat_emb='Aluminium',
            ),
            material_map={'PP': (3.0, 0.0), 'Aluminium': (11.0, 0.0)},
            eol_material_map={},  # ni PP ni Alu mappés EoL pour les packagings
            filiere_map={'NB': (0.943, 0.50, 'DASRI')},
        )
        calc = CarbonCalculator(dm)
        calc._calculate_mass_based_emissions_old('NB11', 'Tube', quantity=100)
        bd = calc.last_breakdown

        self.assertIn('Aluminium', bd['missing_eol'])
        alu = bd['components'][1]
        self.assertTrue(alu['eol']['missing'])
        self.assertEqual(alu['eol']['co2'], 0.0)

    def test_breakdown_reset_a_chaque_compute(self):
        """compute_emission_data doit reset last_breakdown avant le calcul."""
        dm = _make_dm()
        calc = CarbonCalculator(dm)
        # On simule un breakdown précédent
        calc.last_breakdown = {"sentinelle": "ancien_calcul"}
        # Appel sur un cas qui ne passe PAS par mass-based (catégorie inconnue)
        calc.compute_emission_data({
            'category': 'CatégorieInconnue',
            'subcategory': '', 'subsubcategory': '', 'name': '',
            'value': 0.0, 'days': 1,
        })
        self.assertIsNone(calc.last_breakdown,
                          "last_breakdown doit être reset au début de compute_emission_data")

    def test_incertitude_eol_combinee_en_quadrature(self):
        """L'incertitude EoL doit s'ajouter à celle de la production en quadrature."""
        dm = _make_dm(
            data_masse=self._make_data_masse(masse_g=10.0, materiau='PP'),
            material_map={'PP': (3.0, 0.10)},   # 10% incert sur prod
            filiere_map={'NB': (0.943, 0.50, 'DASRI')},  # 50% incert sur EoL
        )
        calc = CarbonCalculator(dm)
        _, _, unc, _ = calc._calculate_mass_based_emissions_old(
            'NB11', 'Tube', quantity=100,
        )
        # prod emission = 3.0, abs unc prod = 3.0 × 0.10 = 0.30
        # eol  emission = 0.943, abs unc eol = 0.943 × 0.50 = 0.4715
        # combined = sqrt(0.30² + 0.4715²) = sqrt(0.09 + 0.2223) ≈ 0.5588
        expected = (0.30**2 + 0.4715**2) ** 0.5
        self.assertAlmostEqual(unc, expected, places=4)


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

    def test_entree_non_volumique_existante_utilise_grammes(self):
        """Une ancienne entrée non volumique en base liquides peut encore être calculée en grammes."""
        liquid_row = pd.Series({
            'Code NACRES': 'NA73',
            'Produit': 'AGAR AGAR TECHNICAL',
            'Unité': 'g',
            'Facteur CO₂ (kg CO₂e/kg)': 12.0,
            'Incertitude (%)': '',
        })
        dm = _make_dm(liquid_row=liquid_row)
        calc = CarbonCalculator(dm)
        emission, masse, err = calc._calculate_liquid_emissions('NA73', volume_ml=5000)
        self.assertAlmostEqual(masse, 5.0)
        self.assertAlmostEqual(emission, 60.0)
        self.assertEqual(err, 0.0)

    def test_produit_commercial_liquide_utilise_facteur_reference(self):
        """Un solvant commercial stocké en consommable peut pointer vers un facteur liquide."""
        main_data = pd.DataFrame({
            'category': ['Achats'],
            'subcategory': ['Consommables'],
            'subsubcategory': ['NA02'],
            'name': ['SOLVANTS : ACETONE'],
            'year': [''],
            'total': [0.45],
            'uncertainty': [0.0],
            'unit': ['euro'],
        })
        product_row = pd.Series({
            'Code NACRES': 'NA02',
            'Consommable': 'ACETONE TECHNIQUE 5 litres',
            'Volume flacon (mL)': 5000,
            'Facteur liquide source': 'Acétone',
        })
        factor_row = pd.Series({
            'Code NACRES': 'NA02',
            'Produit': 'Acétone',
            'Unité': 'mL',
            'Densité (g/mL)': 0.79,
            'Facteur CO₂ (kg CO₂e/kg)': 2.55,
            'Incertitude (%)': 30.0,
        })
        dm = _make_dm(main_data=main_data, liquid_row=None)
        dm.get_consumable_liquid_factor_data.return_value = (product_row, factor_row)
        dm.get_transport_factor.return_value = (0.0, 0.0)
        calc = CarbonCalculator(dm)

        ep, ep_err, em, em_err, tm, msg = calc.compute_emission_data({
            'category': 'Achats',
            'subcategory': 'Consommables',
            'subsubcategory': 'NA02',
            'name': 'SOLVANTS : ACETONE',
            'value': 10.04,
            'code_nacres': 'NA02',
            'consommable': 'ACETONE TECHNIQUE 5 litres',
            'quantity': 5000,
        })

        self.assertIsNone(msg)
        self.assertAlmostEqual(ep, 4.518)
        self.assertAlmostEqual(tm, 3.95)
        self.assertAlmostEqual(em, 10.0725)
        self.assertAlmostEqual(em_err, 3.02175)


# ─────────────────────────────────────────────────────────────────────────────
# 5. get_material_data — gestion des NaN
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMaterialData(unittest.TestCase):
    """Tests directs sur DataManager.get_material_data (pas de mock)."""

    def _make_real_dm(self, co2_value, uncert_value):
        """Crée un DataManager minimal avec data_materials injectée à la main."""
        from ui.data_manager import DataManager
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


# ─────────────────────────────────────────────────────────────────────────────
# WARN: prefix behavior in compute_emission_data
# ─────────────────────────────────────────────────────────────────────────────

class TestWarnPrefix(unittest.TestCase):
    """Vérifie le comportement du préfixe WARN: lors du calcul des émissions."""

    def _make_solid_data_masse(self, code='AA01', nom='Produit test',
                                masse_g=10.0, materiau='Plastique'):
        return pd.DataFrame([{
            'Code NACRES':               code,
            'Consommable':               nom,
            'Masse unitaire (g)':        masse_g,
            'Matériau consommable':      materiau,
            'Masse unitaire deuxieme materiaux (g)': 0.0,
            'Matériau deuxieme materiaux': '',
            'Masse unitaire troisième materiaux (g)': 0.0,
            'Matériau troisième materiaux': '',
            'Masse emballage unitaire (g)': 0.0,
            'Matériau emballage':         '',
            'Masse condionnement (g)':    0.0,
            'Matériau conditionnement':   '',
            'Nbr par conditionnement':    1,
        }])

    def _make_cc(self, dm):
        cc = CarbonCalculator.__new__(CarbonCalculator)
        cc.dm = dm
        # data/data_masse/data_materials sont des @property qui délèguent à dm
        return cc

    def test_materiau_absent_retourne_warn(self):
        """Matériau renseigné mais absent de la base → msg commence par WARN:."""
        data_masse = self._make_solid_data_masse(
            code='AA01', nom='Produit test', masse_g=10.0, materiau='MatériauInconnu'
        )
        dm = _make_dm(
            data_masse=data_masse,
            material_map={},  # aucun matériau connu
        )
        dm.get_consumable_liquid_factor_data = MagicMock(return_value=(None, None))
        dm.get_liquid_data.return_value = None
        dm.get_transport_factor.return_value = (0.0, 0.0)
        dm.TRANSPORT_DEFAULT = 'Inconnue (défaut)'

        cc = self._make_cc(dm)
        data_dict = {
            'category': 'Achats',
            'subcategory': 'Consommables de laboratoire',
            'subsubcategory': 'AA01',
            'name': 'Réactifs',
            'year': '',
            'value': 10.0,
            'days': 1,
            'code_nacres': 'AA01',
            'consommable': 'Produit test',
            'quantity': 5,
        }
        ep, _, _, _, _, msg = cc.compute_emission_data(data_dict)

        self.assertIsNotNone(msg)
        self.assertTrue(msg.startswith('WARN:'), f"Attendu WARN:, obtenu: {msg!r}")
        # ep doit tout de même être calculé (pas une erreur fatale)
        self.assertGreater(ep, 0.0)

    def test_materiau_connu_pas_de_warn(self):
        """Matériau trouvé → msg = None."""
        data_masse = self._make_solid_data_masse(
            code='AA01', nom='Produit test', masse_g=10.0, materiau='Plastique'
        )
        dm = _make_dm(
            data_masse=data_masse,
            material_map={'Plastique': (2.5, 0.1)},
        )
        dm.get_consumable_liquid_factor_data = MagicMock(return_value=(None, None))
        dm.get_liquid_data.return_value = None
        dm.get_transport_factor.return_value = (0.0, 0.0)
        dm.TRANSPORT_DEFAULT = 'Inconnue (défaut)'

        cc = self._make_cc(dm)
        data_dict = {
            'category': 'Achats',
            'subcategory': 'Consommables de laboratoire',
            'subsubcategory': 'AA01',
            'name': 'Réactifs',
            'year': '',
            'value': 10.0,
            'days': 1,
            'code_nacres': 'AA01',
            'consommable': 'Produit test',
            'quantity': 5,
        }
        _, _, _, _, _, msg = cc.compute_emission_data(data_dict)
        self.assertIsNone(msg)

    def test_pas_de_donnees_retourne_erreur_fatale_non_warn(self):
        """Catégorie introuvable → erreur fatale, pas de préfixe WARN:."""
        dm = _make_dm(
            main_data=pd.DataFrame(columns=[
                'category', 'subcategory', 'subsubcategory', 'name', 'year',
                'total', 'uncertainty', 'unit',
            ]),
        )
        cc = self._make_cc(dm)
        data_dict = {
            'category': 'Achats',
            'subcategory': 'CatégorieInexistante',
            'subsubcategory': '',
            'name': 'NomInexistant',
            'year': '',
            'value': 10.0,
            'days': 1,
            'code_nacres': 'NA',
            'consommable': 'NA',
            'quantity': 1,
        }
        _, _, _, _, _, msg = cc.compute_emission_data(data_dict)
        self.assertIsNotNone(msg)
        self.assertFalse(msg.startswith('WARN:'), f"Erreur fatale ne doit pas être WARN:, obtenu: {msg!r}")


if __name__ == '__main__':
    unittest.main()
