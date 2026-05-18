# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests de non-régression — valeurs CO₂ chiffrées sur données réelles (Phase 1a).

Ces tests utilisent le vrai DataManager SQLite.
Les valeurs numériques ont été capturées le 2026-05-18 et servent de référence :
toute modification qui change ces résultats de plus de 0.01 % doit être intentionnelle.
"""

import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT_DIR)

# D'autres fichiers de test mockent PySide6 au niveau du module.
# On retire ces mocks avant d'importer les vraies dépendances.
for _mod in list(sys.modules):
    if _mod.startswith('PySide6'):
        sys.modules.pop(_mod, None)

from ui.carbon_calculator import CarbonCalculator
from ui.data_manager import DataManager

_SUB_CONSO = (
    "Consommables (Matières premières, produits chimiques/"
    "biologiques et organismes vivants)"
)

TOLERANCE = 1e-4  # écart relatif toléré : 0.01 %


_SQLITE_PATH = os.path.join(ROOT_DIR, "private", "labeco2.sqlite")


def _make_calc():
    dm = DataManager(ROOT_DIR, user_path=ROOT_DIR, sqlite_path=_SQLITE_PATH)
    return CarbonCalculator(dm)


class TestNonRegressionValues(unittest.TestCase):

    def setUp(self):
        self.calc = _make_calc()

    def _assert_close(self, label, actual, expected):
        if expected == 0.0:
            self.assertAlmostEqual(actual, 0.0, places=6, msg=label)
        else:
            rel = abs(actual - expected) / abs(expected)
            self.assertLess(
                rel, TOLERANCE,
                f"{label}: {actual} vs attendu {expected} (écart {rel:.2e})",
            )

    def test_solide_discret_pp_tube_15ml(self):
        """Tube centrifugeuse 15 mL (PP) — CO₂ masse calculé depuis le matériau."""
        ep, ep_err, em, em_err, tm, msg = self.calc.compute_emission_data({
            'category': 'Achats', 'subcategory': _SUB_CONSO,
            'subsubcategory': 'NB11',
            'name': 'MICROTUBES, CRYOTUBES, TUBES A USAGE UNIQUE',
            'value': 10.0, 'code_nacres': 'NB11',
            'consommable': 'Tube centrifugeuse 15 mL', 'quantity': 10,
        })
        self.assertIsNone(msg)
        self._assert_close('ep',     ep,     4.200000)
        self._assert_close('ep_err', ep_err, 1.411200)
        self._assert_close('em',     em,     0.218755)
        self._assert_close('em_err', em_err, 0.020794)
        self._assert_close('tm',     tm,     0.067000)

    def test_liquide_commercial_acetone_1l(self):
        """ACETONE NP 1 litre — lien produit → facteur liquide résolu."""
        ep, ep_err, em, em_err, tm, msg = self.calc.compute_emission_data({
            'category': 'Achats', 'subcategory': _SUB_CONSO,
            'subsubcategory': 'NA02', 'name': 'SOLVANTS : ACETONE',
            'value': 10.0, 'code_nacres': 'NA02',
            'consommable': 'ACETONE NP 1 litre', 'quantity': 1000,
        })
        self.assertIsNone(msg)
        self._assert_close('ep',     ep,     4.500000)
        self._assert_close('ep_err', ep_err, 1.620000)
        self._assert_close('em',     em,     2.223850)
        self._assert_close('em_err', em_err, 0.607605)
        self._assert_close('tm',     tm,     0.790000)

    def test_solide_sans_materiau_prix_seul(self):
        """Seringue sans matériau — em=0, seul le calcul par le prix est disponible."""
        ep, ep_err, em, em_err, tm, msg = self.calc.compute_emission_data({
            'category': 'Achats', 'subcategory': _SUB_CONSO,
            'subsubcategory': 'NB03',
            'name': 'SERINGUES EN PLASTIQUE ET AIGUILLES',
            'value': 23.46, 'code_nacres': 'NB03',
            'consommable': 'SERINGUE STÉRILE 20ml (x50)', 'quantity': 100,
        })
        self.assertIsNone(msg)
        self._assert_close('ep',     ep,     11.495400)
        self._assert_close('ep_err', ep_err, 4.506197)
        self._assert_close('em',     em,     0.0)
        self._assert_close('em_err', em_err, 0.0)
        self._assert_close('tm',     tm,     0.0)

    def test_consommable_absent_fallback_prix(self):
        """Catégorie valide sans consommable sélectionné — seul ep calculé."""
        ep, ep_err, em, em_err, tm, msg = self.calc.compute_emission_data({
            'category': 'Achats', 'subcategory': _SUB_CONSO,
            'subsubcategory': 'NB11',
            'name': 'MICROTUBES, CRYOTUBES, TUBES A USAGE UNIQUE',
            'value': 10.0, 'code_nacres': 'NB11',
            'consommable': '', 'quantity': 0,
        })
        self.assertIsNone(msg)
        self._assert_close('ep',     ep,     4.200000)
        self._assert_close('ep_err', ep_err, 1.411200)
        self._assert_close('em',     em,     0.0)
        self._assert_close('tm',     tm,     0.0)


if __name__ == '__main__':
    unittest.main()
