# SPDX-License-Identifier: GPL-3.0-or-later
"""Détails lisibles pour les entrées de validation SQLite."""

from __future__ import annotations

import sqlite3


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
        f"Type : {product['product_type'] or ''}",
        f"Statut : {product['status'] or ''}",
        f"Prix conditionnement : {product['price_sold_packaging'] or ''}",
        f"Unités / conditionnement : {product['units_per_sold_packaging'] or ''}",
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
    return "\n".join(lines)


def _format_generic_detail(conn: sqlite3.Connection, table: str, entry_id: str) -> str:
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (entry_id,)).fetchone()
    if not row:
        return "Entrée introuvable."
    lines = []
    for key in row.keys():
        value = row[key]
        if value is not None and str(value).strip():
            lines.append(f"{key} : {value}")
    return "\n".join(lines)
