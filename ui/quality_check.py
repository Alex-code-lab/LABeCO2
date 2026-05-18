# SPDX-License-Identifier: GPL-3.0-or-later
"""Règles de validation qualité pour les données LABeCO2.

Deux niveaux d'utilisation :
  - check_row(table, row)  → validations avant écriture d'une seule ligne
  - check_database(conn)   → audit complet d'une base SQLite
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QualityIssue:
    severity: str       # "ERROR" | "WARNING" | "INFO"
    table: str
    rule: str           # identifiant machine de la règle
    message: str        # message lisible
    entry: str = ""     # nom / identifiant de l'entrée concernée
    detail: str = ""    # valeur problématique ou complément


def _clean(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s.lower() in {"nan", "none", "n/a", ""} else s


def _as_float(value: Any) -> float | None:
    try:
        f = float(str(value).replace(",", "."))
        return f if f == f else None   # NaN check
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Règles par ligne (appelées avant écriture)
# ---------------------------------------------------------------------------

def check_commercial_product(row: dict[str, Any]) -> list[QualityIssue]:
    """Vérifie un dictionnaire de produit commercial avant insertion."""
    issues: list[QualityIssue] = []
    name = _clean(row.get("Consommable") or row.get("name", ""))
    is_liquid = _clean(row.get("Unité liquide") or row.get("product_type", "")) in (
        "mL", "L", "liquid"
    )
    factor_id = _clean(row.get("emission_factor_id", ""))
    factor_name = _clean(row.get("Facteur liquide source", ""))
    price = _as_float(row.get("Prix du conditionnement") or row.get("price_sold_packaging"))
    volume = _as_float(row.get("Volume flacon (mL)") or row.get("sold_unit_volume_ml"))

    if is_liquid and not factor_id and not factor_name:
        issues.append(QualityIssue(
            severity="ERROR", table="commercial_products",
            rule="liquid_missing_factor",
            message="Produit liquide sans facteur d'émission lié.",
            entry=name,
        ))

    if is_liquid and volume is None:
        issues.append(QualityIssue(
            severity="ERROR", table="commercial_products",
            rule="liquid_missing_volume",
            message="Produit liquide sans volume vendu par unité.",
            entry=name,
        ))

    if price is not None and price < 0:
        issues.append(QualityIssue(
            severity="ERROR", table="commercial_products",
            rule="negative_price",
            message="Prix négatif.",
            entry=name, detail=str(price),
        ))

    if price is None:
        issues.append(QualityIssue(
            severity="WARNING", table="commercial_products",
            rule="missing_price",
            message="Prix absent (calcul par prix impossible).",
            entry=name,
        ))

    return issues


def check_liquid_factor(row: dict[str, Any]) -> list[QualityIssue]:
    """Vérifie un dictionnaire de facteur liquide avant insertion."""
    issues: list[QualityIssue] = []
    name = _clean(row.get("Produit") or row.get("name", ""))
    source = _clean(row.get("Source") or row.get("source_id", ""))
    co2 = _as_float(row.get("Facteur CO₂ (kg CO₂e/kg)") or row.get("co2_factor"))
    density = _as_float(row.get("Densité (g/mL)") or row.get("density_g_ml"))

    if not source:
        issues.append(QualityIssue(
            severity="ERROR", table="emission_factors",
            rule="factor_missing_source",
            message="Facteur sans source documentée.",
            entry=name,
        ))

    if co2 is not None and (co2 < 0 or co2 > 100):
        issues.append(QualityIssue(
            severity="WARNING", table="emission_factors",
            rule="co2_out_of_range",
            message=f"Facteur CO₂ aberrant : {co2} kg CO₂e/kg (attendu entre 0 et 100).",
            entry=name, detail=str(co2),
        ))

    if density is not None and (density < 0.5 or density > 2.0):
        issues.append(QualityIssue(
            severity="WARNING", table="emission_factors",
            rule="density_out_of_range",
            message=f"Densité hors plage : {density} g/mL (attendu entre 0.5 et 2.0).",
            entry=name, detail=str(density),
        ))

    return issues


def check_material_factor(row: dict[str, Any]) -> list[QualityIssue]:
    """Vérifie un dictionnaire de facteur matériau avant insertion."""
    issues: list[QualityIssue] = []
    name = _clean(row.get("Materiau") or row.get("Produit") or row.get("name", ""))
    source = _clean(row.get("Source") or row.get("source_id", ""))
    co2 = _as_float(
        row.get("Equivalent CO₂ (kg eCO₂/kg)")
        or row.get("Facteur CO₂ (kg CO₂e/kg)")
        or row.get("co2_factor")
    )

    if not source:
        issues.append(QualityIssue(
            severity="ERROR", table="emission_factors",
            rule="factor_missing_source",
            message="Facteur matériau sans source documentée.",
            entry=name,
        ))

    if co2 is not None and (co2 < 0 or co2 > 100):
        issues.append(QualityIssue(
            severity="WARNING", table="emission_factors",
            rule="co2_out_of_range",
            message=f"Facteur CO₂ aberrant : {co2} kg CO₂e/kg.",
            entry=name, detail=str(co2),
        ))

    return issues


# ---------------------------------------------------------------------------
# Audit complet d'une base SQLite
# ---------------------------------------------------------------------------

def _q(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    return conn.execute(sql).fetchall()


def check_database(conn: sqlite3.Connection) -> list[QualityIssue]:
    """Audit qualité complet d'une base SQLite. Retourne toutes les anomalies."""
    issues: list[QualityIssue] = []

    # Produits liquides sans facteur d'émission
    for name, code in _q(conn, """
        SELECT name, code_nacres FROM commercial_products
        WHERE product_type = 'liquid'
          AND (emission_factor_id IS NULL OR emission_factor_id = '')
        ORDER BY code_nacres, name
    """):
        issues.append(QualityIssue(
            severity="ERROR", table="commercial_products",
            rule="liquid_missing_factor",
            message="Produit liquide sans facteur d'émission lié.",
            entry=name, detail=code or "",
        ))

    # Produits liquides sans volume vendu
    for name, code in _q(conn, """
        SELECT name, code_nacres FROM commercial_products
        WHERE product_type = 'liquid'
          AND (sold_unit_volume_ml IS NULL OR sold_unit_volume_ml <= 0)
        ORDER BY code_nacres, name
    """):
        issues.append(QualityIssue(
            severity="ERROR", table="commercial_products",
            rule="liquid_missing_volume",
            message="Produit liquide sans volume vendu par unité.",
            entry=name, detail=code or "",
        ))

    # Prix négatifs
    for name, price in _q(conn, """
        SELECT name, price_sold_packaging FROM commercial_products
        WHERE price_sold_packaging IS NOT NULL AND price_sold_packaging < 0
    """):
        issues.append(QualityIssue(
            severity="ERROR", table="commercial_products",
            rule="negative_price",
            message="Prix négatif.",
            entry=name, detail=str(price),
        ))

    # Facteurs sans source
    for name, ftype in _q(conn, """
        SELECT name, factor_type FROM emission_factors
        WHERE source_id IS NULL OR source_id = ''
        ORDER BY factor_type, name
    """):
        issues.append(QualityIssue(
            severity="ERROR", table="emission_factors",
            rule="factor_missing_source",
            message="Facteur sans source documentée.",
            entry=name, detail=ftype or "",
        ))

    # Facteur CO2 aberrant
    for name, co2 in _q(conn, """
        SELECT name, co2_factor FROM emission_factors
        WHERE co2_factor IS NOT NULL AND (co2_factor < 0 OR co2_factor > 100)
    """):
        issues.append(QualityIssue(
            severity="WARNING", table="emission_factors",
            rule="co2_out_of_range",
            message=f"Facteur CO₂ aberrant : {co2} kg CO₂e/kg.",
            entry=name, detail=str(co2),
        ))

    # Densité liquide hors plage
    for name, density in _q(conn, """
        SELECT name, density_g_ml FROM emission_factors
        WHERE density_g_ml IS NOT NULL AND (density_g_ml < 0.5 OR density_g_ml > 2.0)
        AND factor_type = 'liquid'
    """):
        issues.append(QualityIssue(
            severity="WARNING", table="emission_factors",
            rule="density_out_of_range",
            message=f"Densité hors plage : {density} g/mL.",
            entry=name, detail=str(density),
        ))

    # Doublons suspects dans les produits commerciaux
    for name, code, n in _q(conn, """
        SELECT name, code_nacres, COUNT(*) AS n
        FROM commercial_products
        GROUP BY lower(trim(name)), code_nacres
        HAVING n > 1
        ORDER BY n DESC, name
    """):
        issues.append(QualityIssue(
            severity="WARNING", table="commercial_products",
            rule="duplicate_product",
            message=f"Doublon probable ({n} occurrences).",
            entry=name, detail=code or "",
        ))

    # Entrées en draft (informatif)
    _name_col = {
        "commercial_products": "name",
        "emission_factors": "name",
        "materials": "name",
        "transport_factors": "origin",
    }
    for table in ("commercial_products", "emission_factors", "materials", "transport_factors"):
        col = _name_col[table]
        for (name,) in _q(conn, f"""
            SELECT {col} FROM {table} WHERE status = 'draft' ORDER BY {col}
        """):
            issues.append(QualityIssue(
                severity="INFO", table=table,
                rule="draft_entry",
                message="Entrée non validée (statut draft).",
                entry=name,
            ))

    return issues


def errors(issues: list[QualityIssue]) -> list[QualityIssue]:
    return [i for i in issues if i.severity == "ERROR"]


def warnings(issues: list[QualityIssue]) -> list[QualityIssue]:
    return [i for i in issues if i.severity == "WARNING"]


def format_issues(issues: list[QualityIssue], *, include_info: bool = False) -> str:
    lines = []
    for i in issues:
        if i.severity == "INFO" and not include_info:
            continue
        detail = f" ({i.detail})" if i.detail else ""
        lines.append(f"[{i.severity}] {i.table} — {i.message} : {i.entry}{detail}")
    return "\n".join(lines)
