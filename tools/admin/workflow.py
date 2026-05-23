# SPDX-License-Identifier: GPL-3.0-or-later
"""Règles métier communes au cycle admin LABeCO2."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from ui.sqlite_schema import ensure_app_schema


PENDING = "pending"
DRAFT = "draft"
VALIDATED = "validated"
DEPRECATED = "deprecated"
NON_FINAL_STATUSES = {PENDING, DRAFT}
FINAL_STATUSES = {VALIDATED, DEPRECATED}

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


@dataclass(frozen=True)
class AdminIssue:
    severity: str
    table: str
    rule: str
    message: str
    entry_id: str = ""
    entry: str = ""
    detail: str = ""


@dataclass
class PromotionResult:
    promoted: list[str]
    blocked: dict[str, list[AdminIssue]]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
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
    row: dict,
    detail: str = "",
) -> AdminIssue:
    label = clean(row.get("name") or row.get("title") or row.get("origin") or row.get("id"))
    return AdminIssue(
        severity=severity,
        table=table,
        rule=rule,
        message=message,
        entry_id=clean(row.get("id")),
        entry=label,
        detail=detail,
    )


def check_entry_quality(conn: sqlite3.Connection, table: str, row: dict) -> list[AdminIssue]:
    """Retourne les erreurs bloquantes et warnings pour une ligne métier."""
    issues: list[AdminIssue] = []

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


def blocking_issues(issues: Iterable[AdminIssue]) -> list[AdminIssue]:
    return [issue for issue in issues if issue.severity == "ERROR"]


def check_entries_quality(
    conn: sqlite3.Connection,
    entries: Iterable[tuple[str, str]],
) -> dict[tuple[str, str], list[AdminIssue]]:
    result: dict[tuple[str, str], list[AdminIssue]] = {}
    for table, row_id in entries:
        row = fetch_row(conn, table, row_id)
        if not row:
            result[(table, row_id)] = [
                AdminIssue("ERROR", table, "missing_row", "Entrée introuvable.", row_id)
            ]
            continue
        result[(table, row_id)] = check_entry_quality(conn, table, row)
    return result


def promotable_pending_products(
    conn: sqlite3.Connection,
    product_ids: Iterable[str] | None = None,
) -> PromotionResult:
    ensure_app_schema(conn)
    ids = set(product_ids or [])
    params: list[Any] = []
    where = "WHERE status = 'pending'"
    if ids:
        placeholders = ",".join("?" * len(ids))
        where += f" AND id IN ({placeholders})"
        params.extend(sorted(ids))

    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"SELECT * FROM commercial_products {where}", params).fetchall()
    promoted: list[str] = []
    blocked: dict[str, list[AdminIssue]] = {}
    for row_obj in rows:
        row = dict(row_obj)
        issues = blocking_issues(check_entry_quality(conn, "commercial_products", row))
        if issues:
            blocked[row["id"]] = issues
        else:
            promoted.append(row["id"])
    return PromotionResult(promoted=promoted, blocked=blocked)


def promote_pending_products(
    conn: sqlite3.Connection,
    product_ids: Iterable[str] | None = None,
) -> PromotionResult:
    result = promotable_pending_products(conn, product_ids)
    if result.promoted:
        now = now_iso()
        conn.executemany(
            "UPDATE commercial_products SET status = 'draft', updated_at = ? WHERE id = ?",
            [(now, product_id) for product_id in result.promoted],
        )
    return result


def format_issues(issues: Iterable[AdminIssue], *, max_items: int = 12) -> str:
    selected = list(issues)
    lines = [
        f"[{SEVERITY_LABELS.get(issue.severity, issue.severity)}] "
        f"{TABLE_LABELS.get(issue.table, issue.table)} {issue.entry or issue.entry_id} - {issue.message}"
        + (f" ({issue.detail})" if issue.detail else "")
        for issue in selected[:max_items]
    ]
    if len(selected) > max_items:
        lines.append(f"... {len(selected) - max_items} autre(s) anomalie(s)")
    return "\n".join(lines)
