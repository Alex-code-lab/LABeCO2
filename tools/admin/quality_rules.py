# SPDX-License-Identifier: GPL-3.0-or-later
"""Moteur commun des règles qualité LABeCO2.

Ce module ne dépend pas de Qt. Il centralise les règles utilisées par :
- l'audit global de la base ;
- la validation admin avant changement de statut ;
- les écritures historiques depuis formulaires/CSV.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable


PENDING = "pending"
DRAFT = "draft"
VALIDATED = "validated"
DEPRECATED = "deprecated"

TABLE_LABELS = {
    "contributors": "Contributeurs",
    "sources": "Sources",
    "emission_factors": "Facteurs d'émission",
    "materials": "Matériaux",
    "commercial_products": "Consommables",
    "product_components": "Composants",
    "transport_factors": "Transport",
}

SEVERITY_LABELS = {
    "ERROR": "Erreur",
    "WARNING": "Avertissement",
    "INFO": "Info",
}

_NACRES_RE = re.compile(r"^[A-Z]{2}[0-9]{2}$")


@dataclass
class QualityIssue:
    severity: str
    table: str
    rule: str
    message: str
    entry: str = ""
    detail: str = ""
    row_id: str = ""
    aux_id: str = ""
    related_ids: tuple[str, ...] = ()

    @property
    def entry_id(self) -> str:
        """Compatibilité avec l'ancien type AdminIssue."""
        return self.row_id

    @property
    def blocking(self) -> bool:
        return self.severity == "ERROR"


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "n/a"} else text


def normalized_key(*parts: Any) -> str:
    return "|".join(" ".join(clean(part).lower().split()) for part in parts if clean(part))


def as_float(value: Any) -> float | None:
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def fetch_row(conn: sqlite3.Connection, table: str, row_id: str) -> dict | None:
    conn.row_factory = sqlite3.Row
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    return dict(row) if row else None


def nacres_status(conn: sqlite3.Connection, code: str) -> str:
    code = clean(code).upper()
    if not code:
        return ""
    columns = table_columns(conn, "nacres_codes")
    if not columns:
        return ""
    status_col = "statut_maj_2026" if "statut_maj_2026" in columns else "''"
    row = conn.execute(
        f"SELECT {status_col} FROM nacres_codes WHERE code = ? LIMIT 1",
        (code,),
    ).fetchone()
    return clean(row[0]) if row else ""


def nacres_exists(conn: sqlite3.Connection, code: str) -> bool:
    code = clean(code).upper()
    if not _NACRES_RE.match(code):
        return False
    if not table_columns(conn, "nacres_codes"):
        return True
    return conn.execute("SELECT 1 FROM nacres_codes WHERE code = ?", (code,)).fetchone() is not None


def has_purchase_factor(conn: sqlite3.Connection, code: str) -> bool:
    code = clean(code).upper()
    if not code or not table_columns(conn, "purchase_factors"):
        return False
    like = f"{code}%"
    return conn.execute(
        """
        SELECT 1
        FROM purchase_factors
        WHERE category = 'Achats'
          AND subcategory LIKE 'Consommables%'
          AND subsubcategory LIKE ?
        LIMIT 1
        """,
        (like,),
    ).fetchone() is not None


def _issue(
    severity: str,
    table: str,
    rule: str,
    message: str,
    row: dict[str, Any],
    detail: str = "",
) -> QualityIssue:
    label = clean(row.get("name") or row.get("title") or row.get("origin") or row.get("id"))
    return QualityIssue(
        severity=severity,
        table=table,
        rule=rule,
        message=message,
        entry=label,
        detail=detail,
        row_id=clean(row.get("id")),
    )


def check_entry_quality(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> list[QualityIssue]:
    """Contrôle qualité d'une ligne déjà normalisée dans le schéma SQLite."""
    issues: list[QualityIssue] = []

    if table == "commercial_products":
        name = clean(row.get("name"))
        reference = clean(row.get("reference"))
        code = clean(row.get("code_nacres")).upper()
        product_type = clean(row.get("product_type"))
        packaging = clean(row.get("sold_packaging_label"))
        units_per_pack = as_float(row.get("units_per_sold_packaging"))
        price = as_float(row.get("price_sold_packaging"))

        if not name:
            issues.append(_issue("ERROR", table, "missing_name", "Produit sans nom.", row))
        if not reference:
            issues.append(_issue("ERROR", table, "missing_reference", "Produit sans référence.", row))
        if not product_type:
            issues.append(_issue("ERROR", table, "missing_product_type", "Produit sans type solide/liquide.", row))
        if not packaging and not (units_per_pack is not None and units_per_pack > 0):
            issues.append(_issue("WARNING", table, "missing_packaging", "Produit sans conditionnement.", row))
        if not code:
            issues.append(_issue("ERROR", table, "missing_nacres", "Produit sans code NACRES.", row))
        elif not nacres_exists(conn, code):
            issues.append(_issue("ERROR", table, "invalid_nacres", "Code NACRES inconnu ou invalide.", row, code))
        elif nacres_status(conn, code) == "a_ne_plus_utiliser":
            issues.append(_issue("WARNING", table, "deprecated_nacres", "Code NACRES à ne plus utiliser (non bloquant).", row, code))
        elif nacres_status(conn, code) == "nouveau" and not has_purchase_factor(conn, code):
            issues.append(_issue(
                "WARNING",
                table,
                "new_nacres_without_fe",
                "Nouveau code NACRES 2026 sans facteur d'émission GES 1point5.",
                row,
                code,
            ))

        if product_type == "liquid":
            if not clean(row.get("emission_factor_id")):
                issues.append(_issue(
                    "WARNING",
                    table,
                    "liquid_missing_factor",
                    "Produit liquide sans facteur liquide lié : calcul volume indisponible, calcul prix/NACRES possible.",
                    row,
                ))
            if as_float(row.get("sold_unit_volume_ml")) is None:
                issues.append(_issue("ERROR", table, "liquid_missing_volume", "Produit liquide sans volume vendu.", row))
        elif product_type == "solid":
            count = conn.execute(
                "SELECT COUNT(*) FROM product_components WHERE product_id = ? AND mass_g IS NOT NULL",
                (row.get("id"),),
            ).fetchone()[0]
            if clean(row.get("status")) in {DRAFT, VALIDATED} and count == 0:
                issues.append(_issue("WARNING", table, "solid_missing_components", "Produit solide sans composant massique.", row))

        if price is None:
            issues.append(_issue("WARNING", table, "missing_price", "Prix absent.", row))
        elif price < 0:
            issues.append(_issue("ERROR", table, "negative_price", "Prix négatif.", row, str(price)))

    elif table == "emission_factors":
        if not clean(row.get("name")):
            issues.append(_issue("ERROR", table, "missing_name", "Facteur sans nom.", row))
        if not clean(row.get("source_id")):
            issues.append(_issue("ERROR", table, "factor_missing_source", "Facteur sans source documentée.", row))
        co2 = as_float(row.get("co2_factor"))
        if co2 is None:
            if clean(row.get("factor_type")) == "liquid":
                issues.append(_issue(
                    "WARNING",
                    table,
                    "missing_co2_factor",
                    "Facteur liquide sans valeur CO₂ : calcul volume indisponible, calcul prix/NACRES possible.",
                    row,
                ))
            else:
                issues.append(_issue("ERROR", table, "missing_co2_factor", "Facteur sans valeur CO₂.", row))
        elif co2 < 0 or co2 > 100:
            issues.append(_issue("WARNING", table, "co2_out_of_range", "Facteur CO₂ hors plage.", row, str(co2)))

    elif table == "materials":
        if not clean(row.get("name")):
            issues.append(_issue("ERROR", table, "missing_name", "Matériau sans nom.", row))
        factor_id = clean(row.get("emission_factor_id"))
        if not factor_id:
            issues.append(_issue("ERROR", table, "material_missing_factor", "Matériau sans facteur lié.", row))
        elif not fetch_row(conn, "emission_factors", factor_id):
            issues.append(_issue("ERROR", table, "material_factor_missing", "Facteur matériau introuvable.", row, factor_id))

    elif table == "product_components":
        product_id = clean(row.get("product_id"))
        material_id = clean(row.get("material_id"))
        if not product_id or not fetch_row(conn, "commercial_products", product_id):
            issues.append(_issue("ERROR", table, "component_product_missing", "Produit composant introuvable.", row, product_id))
        if not material_id or not fetch_row(conn, "materials", material_id):
            issues.append(_issue("ERROR", table, "component_material_missing", "Matériau composant introuvable.", row, material_id))
        if as_float(row.get("mass_g")) is None:
            issues.append(_issue("WARNING", table, "component_missing_mass", "Composant sans masse.", row))

    elif table == "transport_factors":
        if not clean(row.get("origin")):
            issues.append(_issue("ERROR", table, "missing_origin", "Transport sans origine.", row))
        if not clean(row.get("mode")):
            issues.append(_issue("ERROR", table, "missing_mode", "Transport sans mode.", row))
        if as_float(row.get("factor_kgco2e_per_kg")) is None:
            issues.append(_issue("ERROR", table, "missing_transport_factor", "Transport sans facteur.", row))

    elif table == "sources":
        if not clean(row.get("title")):
            issues.append(_issue("ERROR", table, "missing_title", "Source sans titre.", row))
        if not (clean(row.get("url")) or clean(row.get("doi")) or clean(row.get("citation"))):
            issues.append(_issue("WARNING", table, "source_missing_locator", "Source sans URL, DOI ou citation.", row))

    elif table == "contributors":
        if not clean(row.get("name")):
            issues.append(_issue("ERROR", table, "missing_name", "Contributeur sans nom.", row))

    return issues


def check_entries_quality(
    conn: sqlite3.Connection,
    entries: Iterable[tuple[str, str]],
) -> dict[tuple[str, str], list[QualityIssue]]:
    result: dict[tuple[str, str], list[QualityIssue]] = {}
    for table, row_id in entries:
        row = fetch_row(conn, table, row_id)
        if not row:
            result[(table, row_id)] = [
                QualityIssue("ERROR", table, "missing_row", "Entrée introuvable.", row_id=row_id)
            ]
            continue
        result[(table, row_id)] = check_entry_quality(conn, table, row)
    return result


def check_commercial_product(row: dict[str, Any]) -> list[QualityIssue]:
    """Vérifie un dictionnaire de produit commercial avant insertion."""
    issues: list[QualityIssue] = []
    name = clean(row.get("Consommable") or row.get("name", ""))
    is_liquid = clean(row.get("Unité liquide") or row.get("product_type", "")) in (
        "mL", "L", "liquid"
    )
    factor_id = clean(row.get("emission_factor_id", ""))
    factor_name = clean(row.get("Facteur liquide source", ""))
    price = as_float(row.get("Prix du conditionnement") or row.get("price_sold_packaging"))
    volume = as_float(row.get("Volume flacon (mL)") or row.get("sold_unit_volume_ml"))

    if is_liquid and not factor_id and not factor_name:
        issues.append(QualityIssue(
            severity="WARNING", table="commercial_products",
            rule="liquid_missing_factor",
            message="Produit liquide sans facteur liquide lié : calcul volume indisponible, calcul prix/NACRES possible.",
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
    name = clean(row.get("Produit") or row.get("name", ""))
    source = clean(row.get("Source") or row.get("source_id", ""))
    co2 = as_float(row.get("Facteur CO₂ (kg CO₂e/kg)") or row.get("co2_factor"))
    density = as_float(row.get("Densité (g/mL)") or row.get("density_g_ml"))

    if not source:
        issues.append(QualityIssue(
            severity="ERROR", table="emission_factors",
            rule="factor_missing_source",
            message="Facteur sans source documentée.",
            entry=name,
        ))

    if co2 is None:
        issues.append(QualityIssue(
            severity="WARNING", table="emission_factors",
            rule="missing_co2_factor",
            message="Facteur liquide sans valeur CO₂ : calcul volume indisponible, calcul prix/NACRES possible.",
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
    name = clean(row.get("Materiau") or row.get("Produit") or row.get("name", ""))
    source = clean(row.get("Source") or row.get("source_id", ""))
    co2 = as_float(
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

    if co2 is None:
        issues.append(QualityIssue(
            severity="ERROR", table="emission_factors",
            rule="missing_co2_factor",
            message="Facteur matériau sans valeur CO₂.",
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


def _q(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    return conn.execute(sql).fetchall()


def check_database(conn: sqlite3.Connection) -> list[QualityIssue]:
    """Audit qualité complet d'une base SQLite. Retourne toutes les anomalies."""
    issues: list[QualityIssue] = []

    for prod_id, name, reference, code, ptype in _q(conn, """
        SELECT id, name, reference, code_nacres, product_type
        FROM commercial_products
        WHERE status != 'deprecated'
          AND (
              name IS NULL OR trim(name) = ''
           OR reference IS NULL OR trim(reference) = ''
           OR code_nacres IS NULL OR trim(code_nacres) = ''
           OR product_type IS NULL OR trim(product_type) = ''
          )
        ORDER BY name
    """):
        missing = []
        if not clean(name):
            missing.append("nom")
        if not clean(reference):
            missing.append("référence")
        if not clean(code):
            missing.append("NACRES")
        if not clean(ptype):
            missing.append("type")
        issues.append(QualityIssue(
            severity="ERROR", table="commercial_products",
            rule="product_missing_admin_fields",
            message="Produit incomplet avant validation.",
            entry=name or prod_id, detail=", ".join(missing),
            row_id=prod_id or "",
        ))

    if "statut_maj_2026" in table_columns(conn, "nacres_codes"):
        for name, code, prod_id in _q(conn, """
            SELECT cp.name, cp.code_nacres, cp.id
            FROM commercial_products cp
            JOIN nacres_codes n ON n.code = cp.code_nacres
            WHERE cp.status != 'deprecated'
              AND n.statut_maj_2026 = 'a_ne_plus_utiliser'
            ORDER BY cp.code_nacres, cp.name
        """):
            issues.append(QualityIssue(
                severity="WARNING", table="commercial_products",
                rule="deprecated_nacres",
                message="Code NACRES à ne plus utiliser (non bloquant).",
                entry=name, detail=code or "",
                row_id=prod_id or "",
            ))

    for name, code, prod_id in _q(conn, """
        SELECT name, code_nacres, id FROM commercial_products
        WHERE status != 'deprecated'
          AND (sold_packaging_label IS NULL OR trim(sold_packaging_label) = '')
          AND (units_per_sold_packaging IS NULL OR units_per_sold_packaging <= 0)
        ORDER BY code_nacres, name
    """):
        issues.append(QualityIssue(
            severity="WARNING", table="commercial_products",
            rule="missing_packaging",
            message="Produit sans conditionnement.",
            entry=name, detail=code or "",
            row_id=prod_id or "",
        ))

    for name, code, prod_id in _q(conn, """
        SELECT name, code_nacres, id FROM commercial_products
        WHERE product_type = 'liquid'
          AND (emission_factor_id IS NULL OR emission_factor_id = '')
        ORDER BY code_nacres, name
    """):
        issues.append(QualityIssue(
            severity="WARNING", table="commercial_products",
            rule="liquid_missing_factor",
            message="Produit liquide sans facteur liquide lié : calcul volume indisponible, calcul prix/NACRES possible.",
            entry=name, detail=code or "",
            row_id=prod_id or "",
        ))

    for name, code, prod_id in _q(conn, """
        SELECT name, code_nacres, id FROM commercial_products
        WHERE product_type = 'liquid'
          AND (sold_unit_volume_ml IS NULL OR sold_unit_volume_ml <= 0)
        ORDER BY code_nacres, name
    """):
        issues.append(QualityIssue(
            severity="WARNING", table="commercial_products",
            rule="liquid_missing_volume",
            message="Produit liquide sans volume vendu par unité.",
            entry=name, detail=code or "",
            row_id=prod_id or "",
        ))

    for name, price, prod_id in _q(conn, """
        SELECT name, price_sold_packaging, id FROM commercial_products
        WHERE price_sold_packaging IS NOT NULL AND price_sold_packaging < 0
    """):
        issues.append(QualityIssue(
            severity="ERROR", table="commercial_products",
            rule="negative_price",
            message="Prix négatif.",
            entry=name, detail=str(price),
            row_id=prod_id or "",
        ))

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

    if table_exists(conn, "product_components"):
        for comp_id, product_id in _q(conn, """
            SELECT pc.id, pc.product_id
            FROM product_components pc
            LEFT JOIN commercial_products cp ON cp.id = pc.product_id
            WHERE cp.id IS NULL
        """):
            issues.append(QualityIssue(
                severity="ERROR", table="product_components",
                rule="component_product_missing",
                message="Composant orphelin (produit parent supprimé).",
                entry=f"composant {comp_id[:8]}...", detail=f"product_id={product_id or '?'}",
                aux_id=comp_id or "",
            ))
        for comp_id, material_id, product_name, product_id in _q(conn, """
            SELECT pc.id, pc.material_id,
                   COALESCE(cp.name, pc.product_id) AS product_name,
                   pc.product_id
            FROM product_components pc
            LEFT JOIN materials m ON m.id = pc.material_id
            LEFT JOIN commercial_products cp ON cp.id = pc.product_id
            WHERE m.id IS NULL
              AND NOT (pc.component_type = 'product' AND pc.material_id IS NULL)
        """):
            if material_id is None:
                detail = "composant sans matériau lié (données orphelines)"
                msg = "Ligne de composition sans matériau associé (peut être supprimée)."
            else:
                detail = f"material_id introuvable : {material_id[:12]}..."
                msg = "Composant pointant vers un matériau supprimé."
            issues.append(QualityIssue(
                severity="ERROR", table="product_components",
                rule="component_material_missing",
                message=msg,
                entry=product_name or comp_id,
                detail=detail,
                row_id=product_id or "",
                aux_id=comp_id or "",
            ))

    for factor_id, name, factor_type in _q(conn, """
        SELECT id, name, factor_type FROM emission_factors
        WHERE co2_factor IS NULL
        ORDER BY factor_type, name
    """):
        is_liquid = factor_type == "liquid"
        issues.append(QualityIssue(
            severity="WARNING" if is_liquid else "ERROR",
            table="emission_factors",
            rule="missing_co2_factor",
            message=(
                "Facteur liquide sans valeur CO₂ : calcul volume indisponible, calcul prix/NACRES possible."
                if is_liquid
                else "Facteur sans valeur CO₂."
            ),
            entry=name,
            detail=factor_type or "",
            row_id=factor_id or "",
        ))

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

    for name, code, packaging, ids, n in _q(conn, """
        SELECT name, code_nacres, sold_packaging_label,
               GROUP_CONCAT(id, char(31)) AS ids, COUNT(*) AS n
        FROM commercial_products
        WHERE status != 'deprecated'
        GROUP BY lower(trim(name)),
                 code_nacres,
                 lower(trim(COALESCE(brand, ''))),
                 lower(trim(COALESCE(reference, ''))),
                 lower(trim(COALESCE(sold_packaging_label, ''))),
                 COALESCE(units_per_sold_packaging, -1),
                 lower(trim(COALESCE(product_type, '')))
        HAVING n > 1
        ORDER BY n DESC, name
    """):
        related_ids = tuple(part for part in str(ids or "").split(chr(31)) if part)
        detail = " | ".join(part for part in (code or "", packaging or "") if part)
        issues.append(QualityIssue(
            severity="WARNING", table="commercial_products",
            rule="duplicate_product",
            message=f"Doublon probable ({n} occurrences).",
            entry=name, detail=detail,
            related_ids=related_ids,
        ))

    name_col = {
        "commercial_products": "name",
        "emission_factors": "name",
        "materials": "name",
        "transport_factors": "origin",
    }
    for table in ("commercial_products", "emission_factors", "materials", "transport_factors"):
        col = name_col[table]
        for (name,) in _q(conn, f"""
            SELECT {col} FROM {table} WHERE status = 'draft' ORDER BY {col}
        """):
            issues.append(QualityIssue(
                severity="INFO", table=table,
                rule="draft_entry",
                message="Entrée à valider.",
                entry=name,
            ))

    return issues


def blocking_issues(issues: Iterable[QualityIssue]) -> list[QualityIssue]:
    return [issue for issue in issues if issue.severity == "ERROR"]


def errors(issues: Iterable[QualityIssue]) -> list[QualityIssue]:
    return [issue for issue in issues if issue.severity == "ERROR"]


def warnings(issues: Iterable[QualityIssue]) -> list[QualityIssue]:
    return [issue for issue in issues if issue.severity == "WARNING"]


def format_admin_issues(issues: Iterable[QualityIssue], *, max_items: int = 12) -> str:
    selected = list(issues)
    lines = [
        f"[{SEVERITY_LABELS.get(issue.severity, issue.severity)}] "
        f"{TABLE_LABELS.get(issue.table, issue.table)} {issue.entry or issue.row_id} - {issue.message}"
        + (f" ({issue.detail})" if issue.detail else "")
        for issue in selected[:max_items]
    ]
    if len(selected) > max_items:
        lines.append(f"... {len(selected) - max_items} autre(s) anomalie(s)")
    return "\n".join(lines)


def format_issues(issues: Iterable[QualityIssue], *, include_info: bool = False) -> str:
    lines = []
    for issue in issues:
        if issue.severity == "INFO" and not include_info:
            continue
        detail = f" ({issue.detail})" if issue.detail else ""
        lines.append(f"[{issue.severity}] {issue.table} - {issue.message} : {issue.entry}{detail}")
    return "\n".join(lines)
