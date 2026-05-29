# SPDX-License-Identifier: GPL-3.0-or-later
"""Adaptateur SQLite vers les DataFrames historiques de LABeCO2."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from ui.sqlite_schema import ensure_app_schema


COMMERCIAL_PRODUCT_COLUMNS = [
    "Consommable",
    "Marque",
    "Référence",
    "Code CAS",
    "Catégorie",
    "Code NACRES",
    "Masse unitaire (g)",
    "Matériau consommable",
    "Masse unitaire deuxieme materiaux (g)",
    "Matériau deuxieme materiaux",
    "Masse unitaire troisième materiaux (g)",
    "Matériau troisième materiaux",
    "Masse emballage unitaire (g)",
    "Matériau emballage",
    "Nbr par emballage secondaire",
    "Masse condionnement (g)",
    "Matériau conditionnement",
    "Nbr par conditionnement",
    "Prix du conditionnement",
    "Unité liquide",
    "Volume flacon (mL)",
    "Facteur liquide source",
    "date d'ajout",
    "Source",
    "Signature",
    "Source catalogue IJM",
    "Lien / Note / Remarque",
    "condt_ijm",
    "designation_ijm",
    "code_ijm",
    "marque_ijm",
    "score_match",
]

LIQUID_FACTOR_COLUMNS = [
    "Produit",
    "Type",
    "Code NACRES",
    "CAS",
    "Référence",
    "Unité",
    "Densité (g/mL)",
    "Concentration (mg/mL)",
    "Facteur CO₂ (kg CO₂e/kg)",
    "Incertitude (%)",
    "Source",
    "Signature",
    "date d'ajout",
    "Note",
]

MATERIAL_COLUMNS = [
    "Materiau",
    "Equivalent CO₂ (kg eCO₂/kg)",
    "uncertainty",
    "Source",
    "Signature",
]

TRANSPORT_COLUMNS = [
    "Origine",
    "Distance (km)",
    "Mode",
    "Facteur transport (kg CO₂e/kg)",
    "Incertitude",
]

SQLITE_ID_COL = "_sqlite_id"


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "n/a"} else text


def _empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _read_sql(conn: sqlite3.Connection, query: str) -> pd.DataFrame:
    return pd.read_sql_query(query, conn)


def load_legacy_dataframes(sqlite_path: str | Path) -> dict[str, pd.DataFrame]:
    """Charge une base SQLite migrée sous forme de DataFrames historiques."""
    sqlite_path = Path(sqlite_path)
    if not sqlite_path.exists():
        raise FileNotFoundError(f"Base SQLite introuvable : {sqlite_path}")

    with sqlite3.connect(sqlite_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_app_schema(conn)
        return {
            "main_data": load_purchase_factors(conn),
            "data_masse": load_commercial_products(conn),
            "data_materials": load_materials(conn),
            "data_liquides": load_liquid_factors(conn),
            "data_transport": load_transport_factors(conn),
        }


def load_purchase_factors(conn: sqlite3.Connection) -> pd.DataFrame:
    query = """
        SELECT category, subcategory, subsubcategory, unit, name, year, total, uncertainty
        FROM purchase_factors
        ORDER BY rowid
    """
    return _read_sql(conn, query)


def load_materials(conn: sqlite3.Connection) -> pd.DataFrame:
    query = """
        SELECT
            m.name AS "Materiau",
            ef.co2_factor AS "Equivalent CO₂ (kg eCO₂/kg)",
            ef.uncertainty AS "uncertainty",
            s.title AS "Source",
            c.name AS "Signature"
        FROM materials m
        LEFT JOIN emission_factors ef ON ef.id = m.emission_factor_id
        LEFT JOIN sources s ON s.id = m.source_id
        LEFT JOIN contributors c ON c.id = m.contributor_id
        WHERE m.status != 'deprecated'
        ORDER BY m.rowid
    """
    df = _read_sql(conn, query)
    return df.reindex(columns=MATERIAL_COLUMNS) if not df.empty else _empty_frame(MATERIAL_COLUMNS)


def load_liquid_factors(conn: sqlite3.Connection) -> pd.DataFrame:
    query = """
        SELECT
            ef.id AS "factor_id",
            ef.name AS "Produit",
            ef.factor_type AS "Type",
            ef.code_nacres AS "Code NACRES",
            '' AS "CAS",
            '' AS "Référence",
            '' AS "Unité",
            ef.density_g_ml AS "Densité (g/mL)",
            ef.concentration_mg_ml AS "Concentration (mg/mL)",
            ef.co2_factor AS "Facteur CO₂ (kg CO₂e/kg)",
            ef.uncertainty * 100.0 AS "Incertitude (%)",
            s.title AS "Source",
            c.name AS "Signature",
            ef.created_at AS "date d'ajout",
            '' AS "Note"
        FROM emission_factors ef
        LEFT JOIN sources s ON s.id = ef.source_id
        LEFT JOIN contributors c ON c.id = ef.contributor_id
        WHERE ef.factor_type = 'liquid' AND ef.status != 'deprecated'
        ORDER BY ef.rowid
    """
    df = _read_sql(conn, query)
    extra = ["factor_id"]
    return (
        df.reindex(columns=LIQUID_FACTOR_COLUMNS + extra)
        if not df.empty
        else _empty_frame(LIQUID_FACTOR_COLUMNS + extra)
    )


def load_transport_factors(conn: sqlite3.Connection) -> pd.DataFrame:
    query = """
        SELECT
            origin AS "Origine",
            distance_km AS "Distance (km)",
            mode AS "Mode",
            factor_kgco2e_per_kg AS "Facteur transport (kg CO₂e/kg)",
            uncertainty AS "Incertitude"
        FROM transport_factors
        WHERE status != 'deprecated'
        ORDER BY rowid
    """
    df = _read_sql(conn, query)
    return df.reindex(columns=TRANSPORT_COLUMNS) if not df.empty else _empty_frame(TRANSPORT_COLUMNS)


def load_commercial_products(conn: sqlite3.Connection) -> pd.DataFrame:
    products = _read_sql(
        conn,
        """
        SELECT
            cp.id,
            cp.name,
            cp.brand,
            cp.reference,
            cp.code_nacres,
            cp.product_type,
            cp.sold_packaging_label,
            cp.units_per_sold_packaging,
            cp.price_sold_packaging,
            cp.sold_unit_volume_ml,
            cp.capacity_volume_ml,
            cp.emission_factor_id,
            cp.note,
            cp.status,
            cp.revision_of_id,
            ef.name AS factor_name,
            cp.created_at,
            s.title AS source_title,
            c.name AS contributor_name,
            COALESCE(sc.supplier || ' ' || sc.catalogue_date, ijm.source_catalogue) AS source_catalogue,
            COALESCE(sc.conditionnement, ijm.conditionnement) AS catalogue_conditionnement,
            COALESCE(sc.designation,     ijm.designation)     AS catalogue_designation,
            COALESCE(sc.code_fournisseur, ijm.code_ijm)       AS code_ijm,
            COALESCE(sc.brand,           ijm.brand)           AS catalogue_brand
        FROM commercial_products cp
        LEFT JOIN emission_factors ef ON ef.id = cp.emission_factor_id
        LEFT JOIN sources s ON s.id = cp.source_id
        LEFT JOIN contributors c ON c.id = cp.contributor_id
        LEFT JOIN supplier_catalogue sc  ON sc.id  = cp.supplier_catalogue_id
        LEFT JOIN catalogue_ijm      ijm ON ijm.id = cp.ijm_catalogue_id
        WHERE cp.status NOT IN ('deprecated', 'pending')
        ORDER BY cp.rowid
        """,
    )
    if products.empty:
        return _empty_frame(COMMERCIAL_PRODUCT_COLUMNS)

    components = _read_sql(
        conn,
        """
        SELECT
            pc.product_id,
            pc.component_type,
            pc.mass_g,
            pc.units_divisor,
            m.name AS material_name
        FROM product_components pc
        LEFT JOIN materials m ON m.id = pc.material_id
        WHERE pc.mass_g IS NOT NULL
        ORDER BY pc.rowid
        """,
    )
    components_by_product = {
        product_id: group.to_dict("records")
        for product_id, group in components.groupby("product_id", sort=False)
    }

    rows = []
    for product in products.to_dict("records"):
        row = {column: "" for column in COMMERCIAL_PRODUCT_COLUMNS}
        row[SQLITE_ID_COL] = _clean(product["id"])
        row["Consommable"] = _clean(product["name"])
        row["Marque"] = _clean(product["brand"])
        row["Référence"] = _clean(product["reference"])
        row["Catégorie"] = "Consommable"
        row["Code NACRES"] = _clean(product["code_nacres"])
        row["Nbr par conditionnement"] = product["units_per_sold_packaging"]
        row["Prix du conditionnement"] = product["price_sold_packaging"]
        row["Facteur liquide source"] = _clean(product["factor_name"])
        row["Lien / Note / Remarque"] = _clean(product["note"])
        row["Statut validation"] = _clean(product["status"])
        row["Nature validation"] = "Modification" if _clean(product["revision_of_id"]) else "Nouvelle entrée"
        row["revision_of_id"] = _clean(product["revision_of_id"])
        row["emission_factor_id"] = _clean(product["emission_factor_id"])
        row["date d'ajout"] = _clean(product["created_at"])
        row["Source"] = _clean(product["source_title"])
        row["Signature"] = _clean(product["contributor_name"])
        row["Source catalogue IJM"] = _clean(product["source_catalogue"])
        row["condt_ijm"] = _clean(product["sold_packaging_label"]) or _clean(product["catalogue_conditionnement"])
        row["designation_ijm"] = _clean(product["catalogue_designation"])
        row["code_ijm"] = _clean(product["code_ijm"])
        row["marque_ijm"] = _clean(product["catalogue_brand"])

        volume = product["sold_unit_volume_ml"] if product["product_type"] == "liquid" else product["capacity_volume_ml"]
        row["Volume flacon (mL)"] = "" if volume is None else volume
        row["Unité liquide"] = "mL" if product["product_type"] == "liquid" else ""

        _fill_component_columns(row, components_by_product.get(product["id"], []))
        rows.append(row)

    return pd.DataFrame(rows).reindex(
        columns=COMMERCIAL_PRODUCT_COLUMNS + [
            SQLITE_ID_COL,
            "emission_factor_id",
            "Statut validation",
            "Nature validation",
            "revision_of_id",
        ]
    )


def _fill_component_columns(row: dict[str, Any], components: list[dict[str, Any]]) -> None:
    product_slots = [
        ("Masse unitaire (g)", "Matériau consommable"),
        ("Masse unitaire deuxieme materiaux (g)", "Matériau deuxieme materiaux"),
        ("Masse unitaire troisième materiaux (g)", "Matériau troisième materiaux"),
    ]
    product_index = 0
    for component in components:
        component_type = _clean(component.get("component_type"))
        if component_type == "product" and product_index < len(product_slots):
            mass_col, material_col = product_slots[product_index]
            row[mass_col] = component.get("mass_g")
            row[material_col] = _clean(component.get("material_name"))
            product_index += 1
        elif component_type == "secondary_packaging":
            row["Masse emballage unitaire (g)"] = component.get("mass_g")
            row["Matériau emballage"] = _clean(component.get("material_name"))
            row["Nbr par emballage secondaire"] = component.get("units_divisor")
        elif component_type == "primary_packaging":
            row["Masse condionnement (g)"] = component.get("mass_g")
            row["Matériau conditionnement"] = _clean(component.get("material_name"))
