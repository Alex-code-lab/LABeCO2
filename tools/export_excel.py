# SPDX-License-Identifier: GPL-3.0-or-later
"""
Génère le fichier Excel de référence LABeCO2 depuis la base SQLite.

Usage :
    python tools/export_excel.py [--db PATH] [--output FILE]

Options :
    --db PATH       Chemin vers labeco2.sqlite  (défaut : private/labeco2.sqlite)
    --output FILE   Fichier Excel de sortie     (défaut : exports/données_LABeCO2_reference.xlsx)
    --no-quality    Ne pas générer la feuille Contrôles qualité
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui.quality_check import check_database, QualityIssue
from ui.sqlite_schema import ensure_app_schema
DEFAULT_DB = ROOT / "private" / "labeco2.sqlite"
DEFAULT_OUT = ROOT / "exports" / "données_LABeCO2_reference.xlsx"


def query(conn: sqlite3.Connection, sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn)


def sheet_commercial_products(conn: sqlite3.Connection) -> pd.DataFrame:
    return query(conn, """
        SELECT
            cp.name                      AS "Consommable",
            cp.brand                     AS "Marque",
            cp.reference                 AS "Référence",
            cp.code_nacres               AS "Code NACRES",
            cp.product_type              AS "Type",
            cp.sold_packaging_label      AS "Conditionnement vendu",
            cp.units_per_sold_packaging  AS "Unités par conditionnement vendu",
            cp.price_sold_packaging      AS "Prix du conditionnement vendu (€ HT)",
            cp.sold_unit_volume_ml       AS "Volume vendu par unité (mL)",
            cp.capacity_volume_ml        AS "Capacité objet (mL)",
            ef.name                      AS "Facteur liquide / solvant",
            ijm.code_ijm                 AS "Code catalogue IJM",
            ijm.designation              AS "Désignation catalogue IJM",
            ijm.conditionnement          AS "Conditionnement catalogue IJM",
            s.title                      AS "Source",
            cp.note                      AS "Lien / Note / Remarque",
            c.name                       AS "Contributeur",
            cp.status                    AS "Statut",
            cp.created_at                AS "Date d'ajout",
            cp.id                        AS "ID"
        FROM commercial_products cp
        LEFT JOIN emission_factors ef  ON ef.id  = cp.emission_factor_id
        LEFT JOIN catalogue_ijm    ijm ON ijm.id = cp.ijm_catalogue_id
        LEFT JOIN sources          s   ON s.id   = cp.source_id
        LEFT JOIN contributors     c   ON c.id   = cp.contributor_id
        ORDER BY cp.code_nacres, cp.name
    """)


def sheet_product_components(conn: sqlite3.Connection) -> pd.DataFrame:
    return query(conn, """
        SELECT
            cp.name            AS "Consommable",
            cp.code_nacres     AS "Code NACRES",
            pc.component_type  AS "Type composant",
            m.name             AS "Matériau",
            pc.mass_g          AS "Masse (g)",
            pc.units_divisor   AS "Diviseur unités"
        FROM product_components pc
        JOIN  commercial_products cp ON cp.id = pc.product_id
        LEFT JOIN materials       m  ON m.id  = pc.material_id
        ORDER BY cp.code_nacres, cp.name, pc.rowid
    """)


def sheet_liquid_factors(conn: sqlite3.Connection) -> pd.DataFrame:
    return query(conn, """
        SELECT
            ef.name                  AS "Produit",
            ef.code_nacres           AS "Code NACRES",
            ef.co2_factor            AS "Facteur CO₂ (kg CO₂e/kg)",
            CASE WHEN ef.uncertainty IS NOT NULL
                 THEN ef.uncertainty * 100.0 END AS "Incertitude (%)",
            ef.density_g_ml          AS "Densité (g/mL)",
            ef.concentration_mg_ml   AS "Concentration (mg/mL)",
            ef.co2_unit              AS "Unité CO₂",
            s.title                  AS "Source",
            c.name                   AS "Contributeur",
            ef.status                AS "Statut",
            ef.created_at            AS "Date d'ajout",
            ef.id                    AS "ID"
        FROM emission_factors ef
        LEFT JOIN sources      s ON s.id = ef.source_id
        LEFT JOIN contributors c ON c.id = ef.contributor_id
        WHERE ef.factor_type = 'liquid'
        ORDER BY ef.name
    """)


def sheet_material_factors(conn: sqlite3.Connection) -> pd.DataFrame:
    return query(conn, """
        SELECT
            m.name               AS "Matériau",
            ef.co2_factor        AS "Facteur CO₂ matériau (kg eCO₂/kg)",
            ef.uncertainty       AS "Incertitude",
            s.title              AS "Source",
            c.name               AS "Contributeur",
            m.status             AS "Statut",
            m.created_at         AS "Date d'ajout",
            m.id                 AS "ID"
        FROM materials m
        LEFT JOIN emission_factors ef ON ef.id = m.emission_factor_id
        LEFT JOIN sources          s  ON s.id  = m.source_id
        LEFT JOIN contributors     c  ON c.id  = m.contributor_id
        ORDER BY m.name
    """)


def sheet_transport(conn: sqlite3.Connection) -> pd.DataFrame:
    return query(conn, """
        SELECT
            tf.origin                   AS "Origine",
            tf.distance_km              AS "Distance (km)",
            tf.mode                     AS "Mode",
            tf.factor_kgco2e_per_kg     AS "Facteur transport (kg CO₂e/kg)",
            tf.uncertainty              AS "Incertitude",
            s.title                     AS "Source",
            c.name                      AS "Contributeur",
            tf.status                   AS "Statut",
            tf.id                       AS "ID"
        FROM transport_factors tf
        LEFT JOIN sources      s ON s.id = tf.source_id
        LEFT JOIN contributors c ON c.id = tf.contributor_id
        ORDER BY tf.origin
    """)


def sheet_sources(conn: sqlite3.Connection) -> pd.DataFrame:
    return query(conn, """
        SELECT
            title        AS "Titre",
            url          AS "URL",
            doi          AS "DOI",
            citation     AS "Citation",
            source_type  AS "Type",
            status       AS "Statut",
            created_at   AS "Date d'ajout",
            id           AS "ID"
        FROM sources
        ORDER BY title
    """)


def sheet_contributors(conn: sqlite3.Connection) -> pd.DataFrame:
    return query(conn, """
        SELECT
            name        AS "Nom",
            team        AS "Équipe",
            lab         AS "Laboratoire",
            email       AS "Email",
            created_at  AS "Date d'ajout",
            id          AS "ID"
        FROM contributors
        ORDER BY name
    """)


def sheet_catalogue_ijm(conn: sqlite3.Connection) -> pd.DataFrame:
    return query(conn, """
        SELECT
            code_ijm         AS "Code IJM",
            designation      AS "Désignation",
            brand            AS "Marque",
            conditionnement  AS "Conditionnement",
            price_ht         AS "Prix HT (€)",
            units_per_pack   AS "Unités par pack",
            source_catalogue AS "Source catalogue",
            id               AS "ID"
        FROM catalogue_ijm
        ORDER BY code_ijm
    """)


_SEVERITY_FR = {"ERROR": "ERREUR", "WARNING": "AVERTISSEMENT", "INFO": "INFO"}


def sheet_quality(conn: sqlite3.Connection) -> pd.DataFrame:
    """Feuille de contrôles qualité générée depuis ui.quality_check."""
    issues = check_database(conn)
    rows = [
        {
            "Sévérité": _SEVERITY_FR.get(i.severity, i.severity),
            "Table": i.table,
            "Problème": i.message,
            "Entrée": i.entry,
            "Détail": i.detail,
        }
        for i in issues
    ]
    cols = ["Sévérité", "Table", "Problème", "Entrée", "Détail"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Excel LABeCO2 depuis SQLite")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    parser.add_argument("--no-quality", dest="no_quality", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"Base introuvable : {db_path}")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    ensure_app_schema(conn)

    sheets = {
        "Produits commerciaux": sheet_commercial_products(conn),
        "Composants produits":  sheet_product_components(conn),
        "Facteurs liquides":    sheet_liquid_factors(conn),
        "Facteurs matériaux":   sheet_material_factors(conn),
        "Facteurs transport":   sheet_transport(conn),
        "Sources":              sheet_sources(conn),
        "Contributeurs":        sheet_contributors(conn),
        "Catalogue IJM":        sheet_catalogue_ijm(conn),
    }
    if not args.no_quality:
        sheets["Contrôles qualité"] = sheet_quality(conn)

    conn.close()

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"Export : {out_path}")
    for name, df in sheets.items():
        print(f"  {name}: {len(df)} ligne(s)")


if __name__ == "__main__":
    main()
