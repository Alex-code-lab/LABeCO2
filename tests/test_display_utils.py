# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_display_utils.py
#
# Tests unitaires pour ui/display_utils.py — aucune dépendance Qt.

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ui.display_utils import (
    clean_text, safe_float, format_quantity,
    normalize_nacres_prefix, is_consumables_subcategory,
    format_subcategory_label, display_unit,
)


class TestCleanText(unittest.TestCase):

    def test_none_retourne_vide(self):
        self.assertEqual(clean_text(None), "")

    def test_nan_string_retourne_vide(self):
        for val in ("nan", "NaN", "NAN", "none", "None", "NAT", "nat"):
            with self.subTest(val=val):
                self.assertEqual(clean_text(val), "")

    def test_float_nan_retourne_vide(self):
        self.assertEqual(clean_text(float("nan")), "")

    def test_espaces_strippes(self):
        self.assertEqual(clean_text("  AA01  "), "AA01")

    def test_entier_converti(self):
        self.assertEqual(clean_text(42), "42")

    def test_vide_reste_vide(self):
        self.assertEqual(clean_text(""), "")

    def test_chaine_normale(self):
        self.assertEqual(clean_text("Plastique"), "Plastique")


class TestSafeFloat(unittest.TestCase):

    def test_float_normal(self):
        self.assertAlmostEqual(safe_float("3.14"), 3.14)

    def test_virgule_europeenne(self):
        self.assertAlmostEqual(safe_float("3,14"), 3.14)

    def test_entier(self):
        self.assertAlmostEqual(safe_float("42"), 42.0)

    def test_vide_retourne_defaut(self):
        self.assertEqual(safe_float(""), 0.0)

    def test_defaut_personnalise(self):
        self.assertEqual(safe_float("", default=99.0), 99.0)

    def test_nan_retourne_defaut(self):
        self.assertEqual(safe_float("nan"), 0.0)

    def test_non_numerique_retourne_defaut(self):
        self.assertEqual(safe_float("abc"), 0.0)

    def test_none_retourne_defaut(self):
        self.assertEqual(safe_float(None), 0.0)


class TestFormatQuantity(unittest.TestCase):

    def test_entier_sans_decimale(self):
        self.assertEqual(format_quantity(10.0), "10")
        self.assertEqual(format_quantity("5"), "5")

    def test_float_sans_zeros_inutiles(self):
        self.assertEqual(format_quantity(1.5), "1.5")

    def test_zero(self):
        self.assertEqual(format_quantity(0), "0")

    def test_quatre_decimales_utiles(self):
        result = format_quantity(1.2345)
        self.assertEqual(result, "1.2345")


class TestNormalizNacresPrefix(unittest.TestCase):

    def test_code_quatre_chars(self):
        self.assertEqual(normalize_nacres_prefix("AA01"), "AA01")

    def test_code_long_tronque_a_quatre(self):
        self.assertEqual(normalize_nacres_prefix("AA01 Culture cellulaire"), "AA01")

    def test_minuscules_en_majuscules(self):
        self.assertEqual(normalize_nacres_prefix("nb13"), "NB13")

    def test_vide_retourne_vide(self):
        self.assertEqual(normalize_nacres_prefix(""), "")

    def test_code_court_non_tronque(self):
        self.assertEqual(normalize_nacres_prefix("AB1"), "AB1")


class TestIsConsommablesSubcategory(unittest.TestCase):

    def test_consommables_vrai(self):
        self.assertTrue(is_consumables_subcategory("Consommables de laboratoire"))
        self.assertTrue(is_consumables_subcategory("consommables (plastiques)"))
        self.assertTrue(is_consumables_subcategory("CONSOMMABLES"))

    def test_autres_faux(self):
        for val in ("Voiture", "Électricité", "", "Activités"):
            with self.subTest(val=val):
                self.assertFalse(is_consumables_subcategory(val))


class TestFormatSubcategoryLabel(unittest.TestCase):

    def test_avec_parentheses(self):
        label, tooltip = format_subcategory_label("Consommables (Matières premières)")
        self.assertEqual(label, "Consommables")
        self.assertEqual(tooltip, "Matières premières")

    def test_sans_parentheses(self):
        label, tooltip = format_subcategory_label("Consommables de laboratoire")
        self.assertEqual(label, "Consommables")
        self.assertEqual(tooltip, "")

    def test_non_consommable_inchange(self):
        label, tooltip = format_subcategory_label("Voiture")
        self.assertEqual(label, "Voiture")
        self.assertEqual(tooltip, "")


class TestDisplayUnit(unittest.TestCase):

    def test_euro_textuel_converti(self):
        self.assertEqual(display_unit("euro"), "€")
        self.assertEqual(display_unit("Euro"), "€")
        self.assertEqual(display_unit("EURO"), "€")

    def test_autres_inchanges(self):
        self.assertEqual(display_unit("km"), "km")
        self.assertEqual(display_unit("kWh"), "kWh")
        self.assertEqual(display_unit("L"), "L")


if __name__ == "__main__":
    unittest.main()
