# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_reference_excel_export.py

import sys
from unittest.mock import patch

import pandas as pd

from tools.scraping import migrate_ijm_price_schema as migration


def test_reference_excel_separates_commercial_products_and_emission_factors(tmp_path):
    xlsx_path = tmp_path / "donnees_reference.xlsx"
    solid_df = pd.DataFrame([{
        "Consommable": "Tube test",
        "Masse condionnement (g)": 50,
        "Nbr par conditionnement": 100,
        "Volume flacon (mL)": "",
    }])
    liquid_df = pd.DataFrame([{
        "Produit": "Acétone",
        "Densité (g/mL)": 0.79,
        "Facteur CO₂ (kg CO₂e/kg)": 2.5,
    }])
    materials_df = pd.DataFrame([{
        "Materiau": "Verre",
        "Equivalent CO₂ (kg eCO₂/kg)": 1.2,
        "Source": "Base Empreinte",
        "Signature": "Equipe test",
    }])
    transport_df = pd.DataFrame([{
        "Origine": "Europe",
        "Facteur transport (kg CO₂e/kg)": 0.03,
        "Source": "Méthode interne",
        "Signature": "Equipe test",
    }])

    with (
        patch.object(migration, "REFERENCE_XLSX", xlsx_path),
        patch.object(
            migration,
            "migrate_reference_source_signature_columns",
            side_effect=[materials_df, transport_df],
        ),
    ):
        migration.write_reference_excel(solid_df, liquid_df)

    xl = pd.ExcelFile(xlsx_path)
    assert xl.sheet_names == [
        "Produits commerciaux",
        "Facteurs liquides",
        "Facteurs matériaux",
        "Facteurs transport",
    ]

    commercial_headers = list(xl.parse("Produits commerciaux", nrows=0).columns)
    liquid_headers = list(xl.parse("Facteurs liquides", nrows=0).columns)
    material_headers = list(xl.parse("Facteurs matériaux", nrows=0).columns)

    assert "Masse du conditionnement primaire complet ou du contenant vide (g)" in commercial_headers
    assert "Unités par conditionnement vendu" in commercial_headers
    assert "Volume vendu par unité de consommable (mL)" in commercial_headers
    assert "Facteur liquide / solvant" in liquid_headers
    assert "Facteur CO₂ matériau (kg eCO₂/kg)" in material_headers
    assert "Consommables (masse)" not in xl.sheet_names
    assert "Liquides & Solvants" not in xl.sheet_names


def test_reference_source_signature_columns_are_split_with_backup(tmp_path):
    sys.modules.pop("tables", None)
    sys.modules.pop("tables.flavor", None)

    hdf_path = tmp_path / "materials.h5"
    pd.DataFrame([{
        "Materiau": "Verre",
        "Equivalent CO₂ (kg eCO₂/kg)": 1.2,
        "Source/Signature": "Ancienne source documentaire",
    }]).to_hdf(hdf_path, key="data", mode="w")

    migrated = migration.migrate_reference_source_signature_columns(hdf_path)
    reloaded = pd.read_hdf(hdf_path)

    assert "Source/Signature" not in migrated.columns
    assert "Source/Signature" not in reloaded.columns
    assert migrated.loc[0, "Source"] == "Ancienne source documentaire"
    assert migrated.loc[0, "Signature"] == ""
    assert hdf_path.with_suffix(".h5.backup_before_source_signature_split").exists()
