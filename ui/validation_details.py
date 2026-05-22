# SPDX-License-Identifier: GPL-3.0-or-later
"""Détails lisibles pour les entrées de validation SQLite."""

from __future__ import annotations

import sqlite3


_SKIP_DIFF_COLS = {
    "id",
    "status",
    "contribution_id",
    "revision_of_id",
    "validated_by_id",
    "validated_at",
    "deprecated_at",
    "created_at",
    "updated_at",
}

_DIFF_LABELS = {
    "name": "Nom",
    "brand": "Marque",
    "reference": "Référence",
    "code_nacres": "NACRES",
    "product_type": "Type",
    "sold_packaging_label": "Conditionnement",
    "units_per_sold_packaging": "Unités / conditionnement",
    "price_sold_packaging": "Prix conditionnement",
    "sold_unit_volume_ml": "Volume vendu (mL)",
    "capacity_volume_ml": "Capacité (mL)",
    "emission_factor_id": "Facteur d'émission ID",
    "ijm_catalogue_id": "Catalogue IJM ID",
    "source_id": "Source ID",
    "contributor_id": "Contributeur ID",
    "note": "Lien / Note / Remarque",
    "co2_factor": "Facteur CO2",
    "factor_kgco2e_per_kg": "Facteur CO2",
    "density_g_per_ml": "Densité",
    "concentration_mg_per_ml": "Concentration",
    "uncertainty": "Incertitude",
    "origin": "Origine",
    "destination": "Destination",
}

_STATUS_LABELS = {
    "pending": "En attente",
    "draft": "À valider",
    "validated": "Validé",
    "deprecated": "Déprécié",
}

_TYPE_LABELS = {
    "solid": "Solide",
    "liquid": "Liquide",
    "material": "Matériau",
    "transport": "Transport",
    "spend": "Achat",
}


def _row_get(row: sqlite3.Row, key: str, default=None):
    return row[key] if key in row.keys() else default


def _status_label(value) -> str:
    text = "" if value is None else str(value).strip()
    return _STATUS_LABELS.get(text, text)


def _type_label(value) -> str:
    text = "" if value is None else str(value).strip()
    return _TYPE_LABELS.get(text, text)


def _format_display_value(key: str, value) -> str:
    if key == "status":
        return _status_label(value)
    if key in {"product_type", "factor_type"}:
        return _type_label(value)
    return "" if value is None else str(value)


def format_entry_detail(conn: sqlite3.Connection, table: str, entry_id: str) -> str:
    """Retourne un détail lisible pour l'entrée sélectionnée."""
    conn.row_factory = sqlite3.Row
    if table == "commercial_products":
        return _format_product_detail(conn, entry_id)
    return _format_generic_detail(conn, table, entry_id)


def _format_product_detail(conn: sqlite3.Connection, entry_id: str) -> str:
    product = conn.execute(
        """
        SELECT cp.*, ef.name AS factor_name, s.title AS source_title, c.name AS contributor_name
        FROM commercial_products cp
        LEFT JOIN emission_factors ef ON ef.id = cp.emission_factor_id
        LEFT JOIN sources s ON s.id = cp.source_id
        LEFT JOIN contributors c ON c.id = cp.contributor_id
        WHERE cp.id = ?
        """,
        (entry_id,),
    ).fetchone()
    if not product:
        return "Entrée introuvable."

    lines = [
        f"Produit : {product['name']}",
        f"NACRES : {product['code_nacres'] or ''}",
        f"Type : {_type_label(product['product_type'])}",
        f"Statut : {_status_label(product['status'])}",
        f"Nature : {'Modification' if _row_get(product, 'revision_of_id') else 'Nouvelle entrée'}",
        f"Prix conditionnement : {product['price_sold_packaging'] or ''}",
        f"Unités / conditionnement : {product['units_per_sold_packaging'] or ''}",
        f"Lien / Note / Remarque : {_row_get(product, 'note', '') or ''}",
        f"Source : {product['source_title'] or ''}",
        f"Contributeur : {product['contributor_name'] or ''}",
    ]
    if product["product_type"] == "liquid":
        factor_name = product["factor_name"] or "À relier"
        lines.extend([
            "",
            f"Facteur liquide : {factor_name}",
            f"Volume vendu par unité : {product['sold_unit_volume_ml'] or ''} mL",
        ])
    elif product["capacity_volume_ml"] is not None:
        lines.extend(["", f"Capacité informative : {product['capacity_volume_ml']} mL"])

    components = conn.execute(
        """
        SELECT pc.component_type, pc.mass_g, pc.units_divisor,
               m.name AS material_name, ef.co2_factor
        FROM product_components pc
        LEFT JOIN materials m ON m.id = pc.material_id
        LEFT JOIN emission_factors ef ON ef.id = m.emission_factor_id
        WHERE pc.product_id = ?
        ORDER BY pc.rowid
        """,
        (entry_id,),
    ).fetchall()
    complete_components = [comp for comp in components if comp["mass_g"] is not None]
    incomplete_components = [
        comp
        for comp in components
        if comp["mass_g"] is None and (comp["units_divisor"] or 1) > 1
    ]

    lines.append("")
    lines.append(f"Composants détaillés : {len(complete_components)}")
    if not complete_components:
        lines.append("  Aucun composant détaillé.")
    for comp in complete_components:
        material = comp["material_name"] or "matériau non relié"
        mass = f"{comp['mass_g']} g"
        divisor = comp["units_divisor"] or 1
        factor = "" if comp["co2_factor"] is None else f" ; facteur {comp['co2_factor']} kgCO2e/kg"
        lines.append(f"  - {comp['component_type']} : {material} ; masse {mass} ; diviseur {divisor}{factor}")
    if incomplete_components:
        lines.append("")
        lines.append(f"Données composant à compléter : {len(incomplete_components)}")
        for comp in incomplete_components:
            material = comp["material_name"] or "matériau non relié"
            divisor = comp["units_divisor"] or 1
            factor = "" if comp["co2_factor"] is None else f" ; facteur {comp['co2_factor']} kgCO2e/kg"
            lines.append(f"  - {comp['component_type']} : {material} ; masse manquante ; diviseur {divisor}{factor}")
    revision_lines = _format_revision_diff(conn, "commercial_products", product)
    if revision_lines:
        lines.extend(["", *revision_lines])
    return "\n".join(lines)


def _format_generic_detail(conn: sqlite3.Connection, table: str, entry_id: str) -> str:
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (entry_id,)).fetchone()
    if not row:
        return "Entrée introuvable."
    lines = []
    if "revision_of_id" in row.keys():
        lines.append(
            "Nature : Modification"
            if row["revision_of_id"]
            else "Nature : Nouvelle entrée"
        )
    for key in row.keys():
        value = row[key]
        if value is not None and str(value).strip():
            label = _DIFF_LABELS.get(key, key)
            lines.append(f"{label} : {_format_display_value(key, value)}")
    revision_lines = _format_revision_diff(conn, table, row)
    if revision_lines:
        lines.extend(["", *revision_lines])
    return "\n".join(lines)


def _format_revision_diff(conn: sqlite3.Connection, table: str, row: sqlite3.Row) -> list[str]:
    if "revision_of_id" not in row.keys() or not row["revision_of_id"]:
        return []
    previous = conn.execute(
        f"SELECT * FROM {table} WHERE id = ?",
        (row["revision_of_id"],),
    ).fetchone()
    if not previous:
        return [f"Modification de : {row['revision_of_id']} (ancienne entrée introuvable)"]

    previous_label = _revision_label(table, previous)
    lines = [
        f"Modification de : {previous_label} ({row['revision_of_id']})",
        "Changements :",
    ]
    changes = []
    for key in row.keys():
        if key in _SKIP_DIFF_COLS or key not in previous.keys():
            continue
        old_value = previous[key]
        new_value = row[key]
        if (old_value or "") != (new_value or ""):
            label = _DIFF_LABELS.get(key, key)
            changes.append(
                f"  - {label} : {_format_diff_value(key, old_value)} -> {_format_diff_value(key, new_value)}"
            )
    if not changes:
        changes.append("  Aucun changement métier détecté.")
    lines.extend(changes)
    return lines


def _revision_label(table: str, row: sqlite3.Row) -> str:
    if table == "transport_factors":
        return row["origin"] if "origin" in row.keys() and row["origin"] else "entrée précédente"
    for key in ("name", "title"):
        if key in row.keys() and row[key]:
            return row[key]
    return "entrée précédente"


def _format_diff_value(key: str, value) -> str:
    text = _format_display_value(key, value).strip()
    return text if text else "(vide)"
