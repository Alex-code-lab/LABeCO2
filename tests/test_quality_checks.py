# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests des règles de validation qualité (Phase 9)."""

import sqlite3
import unittest

from ui.quality_check import (
    QualityIssue,
    check_commercial_product,
    check_database,
    check_liquid_factor,
    check_material_factor,
    errors,
    warnings,
)


def _errors(issues):
    return [i for i in issues if i.severity == "ERROR"]


def _warnings(issues):
    return [i for i in issues if i.severity == "WARNING"]


# ---------------------------------------------------------------------------
# check_commercial_product
# ---------------------------------------------------------------------------

class TestCheckCommercialProduct(unittest.TestCase):

    def test_liquid_missing_factor_is_error(self):
        row = {"Consommable": "Éthanol 70 %", "Unité liquide": "mL",
               "Volume flacon (mL)": 500, "Prix du conditionnement": 12.0}
        errs = _errors(check_commercial_product(row))
        rules = [e.rule for e in errs]
        self.assertIn("liquid_missing_factor", rules)

    def test_liquid_with_factor_id_no_error(self):
        row = {"Consommable": "Éthanol 70 %", "Unité liquide": "mL",
               "emission_factor_id": "some-uuid",
               "Volume flacon (mL)": 500, "Prix du conditionnement": 12.0}
        errs = _errors(check_commercial_product(row))
        rules = [e.rule for e in errs]
        self.assertNotIn("liquid_missing_factor", rules)

    def test_liquid_with_factor_name_no_error(self):
        row = {"Consommable": "Éthanol 70 %", "Unité liquide": "mL",
               "Facteur liquide source": "Éthanol",
               "Volume flacon (mL)": 500, "Prix du conditionnement": 12.0}
        errs = _errors(check_commercial_product(row))
        self.assertNotIn("liquid_missing_factor", [e.rule for e in errs])

    def test_liquid_missing_volume_is_error(self):
        row = {"Consommable": "X", "Unité liquide": "mL",
               "emission_factor_id": "uuid", "Prix du conditionnement": 5.0}
        errs = _errors(check_commercial_product(row))
        self.assertIn("liquid_missing_volume", [e.rule for e in errs])

    def test_negative_price_is_error(self):
        row = {"Consommable": "Tube", "Prix du conditionnement": -3.0}
        errs = _errors(check_commercial_product(row))
        self.assertIn("negative_price", [e.rule for e in errs])

    def test_missing_price_is_warning(self):
        row = {"Consommable": "Tube"}
        warns = _warnings(check_commercial_product(row))
        self.assertIn("missing_price", [w.rule for w in warns])

    def test_solid_no_factor_no_error(self):
        """Un solide sans facteur est valide (calcul par masse du matériau)."""
        row = {"Consommable": "Boîte Pétri", "Prix du conditionnement": 8.0,
               "Masse unitaire (g)": 5.0, "Matériau consommable": "Verre"}
        errs = _errors(check_commercial_product(row))
        self.assertNotIn("liquid_missing_factor", [e.rule for e in errs])


# ---------------------------------------------------------------------------
# check_liquid_factor
# ---------------------------------------------------------------------------

class TestCheckLiquidFactor(unittest.TestCase):

    def test_missing_source_is_error(self):
        row = {"Produit": "Méthanol", "Facteur CO₂ (kg CO₂e/kg)": 1.2}
        errs = _errors(check_liquid_factor(row))
        self.assertIn("factor_missing_source", [e.rule for e in errs])

    def test_with_source_no_error(self):
        row = {"Produit": "Méthanol", "Source": "Base Empreinte",
               "Facteur CO₂ (kg CO₂e/kg)": 1.2, "Densité (g/mL)": 0.79}
        errs = _errors(check_liquid_factor(row))
        self.assertEqual(errs, [])

    def test_co2_out_of_range_is_warning(self):
        row = {"Produit": "X", "Source": "Src",
               "Facteur CO₂ (kg CO₂e/kg)": 150.0}
        warns = _warnings(check_liquid_factor(row))
        self.assertIn("co2_out_of_range", [w.rule for w in warns])

    def test_co2_zero_no_warning(self):
        row = {"Produit": "X", "Source": "Src",
               "Facteur CO₂ (kg CO₂e/kg)": 0.0}
        warns = _warnings(check_liquid_factor(row))
        self.assertNotIn("co2_out_of_range", [w.rule for w in warns])

    def test_density_out_of_range_is_warning(self):
        row = {"Produit": "X", "Source": "Src",
               "Facteur CO₂ (kg CO₂e/kg)": 2.0, "Densité (g/mL)": 5.0}
        warns = _warnings(check_liquid_factor(row))
        self.assertIn("density_out_of_range", [w.rule for w in warns])

    def test_density_normal_no_warning(self):
        row = {"Produit": "X", "Source": "Src",
               "Facteur CO₂ (kg CO₂e/kg)": 2.0, "Densité (g/mL)": 0.79}
        warns = _warnings(check_liquid_factor(row))
        self.assertNotIn("density_out_of_range", [w.rule for w in warns])


# ---------------------------------------------------------------------------
# check_material_factor
# ---------------------------------------------------------------------------

class TestCheckMaterialFactor(unittest.TestCase):

    def test_missing_source_is_error(self):
        row = {"Materiau": "Verre", "Equivalent CO₂ (kg eCO₂/kg)": 1.2}
        errs = _errors(check_material_factor(row))
        self.assertIn("factor_missing_source", [e.rule for e in errs])

    def test_with_source_no_error(self):
        row = {"Materiau": "Verre", "Source": "Base Empreinte",
               "Equivalent CO₂ (kg eCO₂/kg)": 1.2}
        errs = _errors(check_material_factor(row))
        self.assertEqual(errs, [])


# ---------------------------------------------------------------------------
# check_database (audit complet)
# ---------------------------------------------------------------------------

def _make_db() -> sqlite3.Connection:
    """Crée une mini-base SQLite en mémoire pour les tests d'audit."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE contributors (
            id TEXT PRIMARY KEY, name TEXT, team TEXT, lab TEXT, email TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE sources (
            id TEXT PRIMARY KEY, title TEXT, url TEXT, doi TEXT, citation TEXT,
            source_type TEXT, contributor_id TEXT, created_at TEXT, updated_at TEXT,
            status TEXT DEFAULT 'draft', contribution_id TEXT, revision_of_id TEXT,
            validated_by_id TEXT, validated_at TEXT, deprecated_at TEXT
        );
        CREATE TABLE emission_factors (
            id TEXT PRIMARY KEY, name TEXT, name_key TEXT, factor_type TEXT,
            code_nacres TEXT, co2_factor REAL, co2_unit TEXT, uncertainty REAL,
            density_g_ml REAL, concentration_mg_ml REAL,
            source_id TEXT, contributor_id TEXT,
            created_at TEXT, updated_at TEXT, status TEXT DEFAULT 'draft',
            contribution_id TEXT, revision_of_id TEXT,
            validated_by_id TEXT, validated_at TEXT, deprecated_at TEXT
        );
        CREATE TABLE materials (
            id TEXT PRIMARY KEY, name TEXT, name_key TEXT,
            emission_factor_id TEXT, source_id TEXT, contributor_id TEXT,
            created_at TEXT, updated_at TEXT, status TEXT DEFAULT 'draft',
            contribution_id TEXT, revision_of_id TEXT,
            validated_by_id TEXT, validated_at TEXT, deprecated_at TEXT
        );
        CREATE TABLE commercial_products (
            id TEXT PRIMARY KEY, name TEXT, brand TEXT, reference TEXT,
            code_nacres TEXT, product_type TEXT,
            sold_packaging_label TEXT, units_per_sold_packaging INTEGER,
            price_sold_packaging REAL, sold_unit_volume_ml REAL,
            capacity_volume_ml REAL, emission_factor_id TEXT,
            ijm_catalogue_id TEXT, source_id TEXT, contributor_id TEXT,
            created_at TEXT, updated_at TEXT, status TEXT DEFAULT 'draft',
            contribution_id TEXT, revision_of_id TEXT,
            validated_by_id TEXT, validated_at TEXT, deprecated_at TEXT
        );
        CREATE TABLE transport_factors (
            id TEXT PRIMARY KEY, origin TEXT, distance_km REAL, mode TEXT,
            factor_kgco2e_per_kg REAL, uncertainty REAL,
            source_id TEXT, contributor_id TEXT,
            created_at TEXT, updated_at TEXT, status TEXT DEFAULT 'draft',
            contribution_id TEXT, revision_of_id TEXT,
            validated_by_id TEXT, validated_at TEXT, deprecated_at TEXT
        );
    """)
    return conn


class TestCheckDatabase(unittest.TestCase):

    def test_liquid_product_without_factor_is_error(self):
        conn = _make_db()
        conn.execute("""
            INSERT INTO commercial_products (id, name, code_nacres, product_type, status)
            VALUES ('p1', 'Éthanol sans facteur', 'NA02', 'liquid', 'validated')
        """)
        conn.commit()
        issues = check_database(conn)
        errs = [i for i in issues if i.rule == "liquid_missing_factor"]
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].entry, "Éthanol sans facteur")

    def test_liquid_product_with_factor_no_error(self):
        conn = _make_db()
        conn.execute("""
            INSERT INTO emission_factors (id, name, name_key, factor_type, status)
            VALUES ('ef1', 'Éthanol', 'ethanol', 'liquid', 'validated')
        """)
        conn.execute("""
            INSERT INTO commercial_products
            (id, name, code_nacres, product_type, emission_factor_id,
             sold_unit_volume_ml, status)
            VALUES ('p1', 'Éthanol 500mL', 'NA02', 'liquid', 'ef1', 500, 'validated')
        """)
        conn.commit()
        issues = check_database(conn)
        errs = [i for i in issues if i.rule == "liquid_missing_factor"]
        self.assertEqual(errs, [])

    def test_negative_price_is_error(self):
        conn = _make_db()
        conn.execute("""
            INSERT INTO commercial_products
            (id, name, code_nacres, product_type, price_sold_packaging, status)
            VALUES ('p2', 'Tube bizarre', 'NB11', 'solid', -5.0, 'validated')
        """)
        conn.commit()
        issues = check_database(conn)
        errs = [i for i in issues if i.rule == "negative_price"]
        self.assertEqual(len(errs), 1)

    def test_factor_without_source_is_error(self):
        conn = _make_db()
        conn.execute("""
            INSERT INTO emission_factors
            (id, name, name_key, factor_type, co2_factor, status)
            VALUES ('ef2', 'Acétone', 'acetone', 'liquid', 2.5, 'validated')
        """)
        conn.commit()
        issues = check_database(conn)
        errs = [i for i in issues if i.rule == "factor_missing_source"]
        self.assertEqual(len(errs), 1)

    def test_co2_aberrant_is_warning(self):
        conn = _make_db()
        conn.execute("""
            INSERT INTO emission_factors
            (id, name, name_key, factor_type, co2_factor, source_id, status)
            VALUES ('ef3', 'Bizarre', 'bizarre', 'liquid', 999.0, 's1', 'validated')
        """)
        conn.commit()
        issues = check_database(conn)
        warns = [i for i in issues if i.rule == "co2_out_of_range"]
        self.assertEqual(len(warns), 1)

    def test_solid_with_capacity_no_factor_ok(self):
        """Un solide avec capacity_volume_ml mais sans facteur n'est pas une erreur."""
        conn = _make_db()
        conn.execute("""
            INSERT INTO commercial_products
            (id, name, code_nacres, product_type, capacity_volume_ml, status)
            VALUES ('p3', 'Flacon 300mL vide', 'NB99', 'solid', 300.0, 'validated')
        """)
        conn.commit()
        issues = check_database(conn)
        errs = [i for i in issues if i.rule == "liquid_missing_factor"]
        self.assertEqual(errs, [])

    def test_duplicate_product_is_warning(self):
        conn = _make_db()
        for i in (1, 2):
            conn.execute(f"""
                INSERT INTO commercial_products (id, name, code_nacres, product_type, status)
                VALUES ('p{i}', 'Tube 15mL', 'NB11', 'solid', 'validated')
            """)
        conn.commit()
        issues = check_database(conn)
        warns = [i for i in issues if i.rule == "duplicate_product"]
        self.assertGreaterEqual(len(warns), 1)

    def test_density_out_of_range_warning(self):
        conn = _make_db()
        conn.execute("""
            INSERT INTO emission_factors
            (id, name, name_key, factor_type, density_g_ml, source_id, status)
            VALUES ('ef4', 'Plomb liquide', 'plomb-liquide', 'liquid', 11.3, 's1', 'validated')
        """)
        conn.commit()
        issues = check_database(conn)
        warns = [i for i in issues if i.rule == "density_out_of_range"]
        self.assertEqual(len(warns), 1)


if __name__ == "__main__":
    unittest.main()
