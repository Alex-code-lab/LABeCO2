# SPDX-License-Identifier: GPL-3.0-or-later
"""Écritures SQLite pour les formulaires historiques de LABeCO2."""

from __future__ import annotations

import sqlite3
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from ui.display_utils import (
    clean_text,
    looks_like_liquid_commercial_product,
    normalize_nacres_prefix,
)
from ui.quality_check import (
    check_commercial_product,
    check_liquid_factor,
    check_material_factor,
    errors as quality_errors,
    format_issues,
)
from ui.sqlite_legacy_adapter import SQLITE_ID_COL


UUID_NAMESPACE = uuid.UUID("f2a16a33-77cc-50cb-94df-0bc2d9dba04c")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean_text(value))
    text = text.encode("ascii", "ignore").decode("ascii")
    return " ".join(text.casefold().split())


def stable_id(*parts: Any) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, "::".join(clean_text(p) for p in parts)))


def revision_id() -> str:
    """UUID aléatoire pour une révision (non stable : chaque révision est unique)."""
    return str(uuid.uuid4())


def _prepare_revision(
    conn: sqlite3.Connection,
    table: str,
    entry_id: str,
    name_key_col: str | None = "name_key",
) -> tuple[str, str | None]:
    """Si l'entrée est validated, la déprécie et retourne (new_id, old_id).
    Sinon retourne (entry_id, None) — mise à jour normale.
    Libère la contrainte UNIQUE sur name_key en suffixant ':dep:<8 chars>'."""
    row = conn.execute(f"SELECT status FROM {table} WHERE id = ?", (entry_id,)).fetchone()
    if row and row[0] == "validated":
        if name_key_col:
            conn.execute(
                f"UPDATE {table} SET {name_key_col} = {name_key_col} || ':dep:' || substr(id,1,8),"
                f" status = 'deprecated', deprecated_at = ?, updated_at = ? WHERE id = ?",
                (now_iso(), now_iso(), entry_id),
            )
        else:
            conn.execute(
                f"UPDATE {table} SET status = 'deprecated', deprecated_at = ?, updated_at = ? WHERE id = ?",
                (now_iso(), now_iso(), entry_id),
            )
        return revision_id(), entry_id
    return entry_id, None


def nullable(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.casefold() in {"", "nan", "none", "nat", "n/a"}:
        return None
    return value


def text_or_none(value: Any) -> str | None:
    value = nullable(value)
    return None if value is None else str(value).strip()


def float_or_none(value: Any) -> float | None:
    value = nullable(value)
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def int_or_none(value: Any) -> int | None:
    number = float_or_none(value)
    return None if number is None else int(number)


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_contributor(conn: sqlite3.Connection, name: Any) -> str:
    contributor_name = clean_text(name) or "migration"
    contributor_id = stable_id("contributors", normalize_key(contributor_name))
    conn.execute(
        """
        INSERT INTO contributors(id, name, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET name = excluded.name, updated_at = excluded.updated_at
        """,
        (contributor_id, contributor_name, now_iso(), now_iso()),
    )
    return contributor_id


def ensure_source(
    conn: sqlite3.Connection,
    title: Any,
    contributor_id: str,
    source_type: str = "user",
) -> str:
    source_title = clean_text(title) or "Ajout utilisateur"
    source_id = stable_id("sources", normalize_key(source_title))
    conn.execute(
        """
        INSERT INTO sources(
            id, title, source_type, contributor_id, created_at, updated_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            source_type = excluded.source_type,
            contributor_id = excluded.contributor_id,
            updated_at = excluded.updated_at
        """,
        (source_id, source_title, source_type, contributor_id, now_iso(), now_iso(), "validated"),
    )
    return source_id


def contributor_and_source(conn: sqlite3.Connection, row: dict[str, Any]) -> tuple[str, str]:
    contributor_id = ensure_contributor(conn, row.get("Signature"))
    source_id = ensure_source(conn, row.get("Source"), contributor_id)
    return contributor_id, source_id


def find_liquid_factor_id(conn: sqlite3.Connection, factor_name: Any, code_nacres: Any = "") -> str | None:
    name_key = normalize_key(factor_name)
    if not name_key:
        return None
    code = normalize_nacres_prefix(code_nacres)
    row = conn.execute(
        """
        SELECT id FROM emission_factors
        WHERE factor_type = 'liquid' AND name_key = ? AND (? = '' OR code_nacres = ?)
        ORDER BY CASE WHEN code_nacres = ? THEN 0 ELSE 1 END
        LIMIT 1
        """,
        (name_key, code, code, code),
    ).fetchone()
    if row:
        return row["id"]
    row = conn.execute(
        """
        SELECT id FROM emission_factors
        WHERE factor_type = 'liquid' AND name_key = ?
        LIMIT 1
        """,
        (name_key,),
    ).fetchone()
    return row["id"] if row else None


def find_material_id(conn: sqlite3.Connection, material_name: Any) -> str | None:
    name_key = normalize_key(material_name)
    if not name_key:
        return None
    row = conn.execute("SELECT id FROM materials WHERE name_key = ?", (name_key,)).fetchone()
    return row["id"] if row else None


def upsert_material_factor(sqlite_path: str | Path, row: dict[str, Any]) -> str:
    with connect(sqlite_path) as conn:
        material_id = upsert_material_factor_conn(conn, row)
        conn.commit()
        return material_id


def upsert_material_factor_conn(conn: sqlite3.Connection, row: dict[str, Any]) -> str:
    name = clean_text(row.get("Materiau"))
    if not name:
        raise ValueError("Nom du matériau manquant.")
    errs = quality_errors(check_material_factor(row))
    if errs:
        raise ValueError(format_issues(errs))
    name_key = normalize_key(name)
    canonical_factor_id = stable_id("emission_factors", "material", name_key)
    canonical_material_id = stable_id("materials", name_key)
    factor_id, factor_rev_of = _prepare_revision(conn, "emission_factors", canonical_factor_id)
    material_id, material_rev_of = _prepare_revision(conn, "materials", canonical_material_id)
    contributor_id, source_id = contributor_and_source(conn, row)
    is_revision = bool(factor_rev_of or material_rev_of)
    conn.execute(
        """
        INSERT INTO emission_factors(
            id, name, name_key, factor_type, code_nacres, co2_factor, co2_unit,
            uncertainty, source_id, contributor_id, created_at, updated_at, status, revision_of_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            co2_factor = excluded.co2_factor,
            uncertainty = excluded.uncertainty,
            source_id = excluded.source_id,
            contributor_id = excluded.contributor_id,
            updated_at = excluded.updated_at,
            status = excluded.status
        """,
        (
            factor_id, name, name_key, "material", None,
            float_or_none(row.get("Equivalent CO₂ (kg eCO₂/kg)")),
            "kg CO2e/kg",
            float_or_none(row.get("uncertainty")),
            source_id, contributor_id, now_iso(), now_iso(),
            "draft" if is_revision else "validated",
            factor_rev_of,
        ),
    )
    conn.execute(
        """
        INSERT INTO materials(
            id, name, name_key, emission_factor_id, source_id, contributor_id,
            created_at, updated_at, status, revision_of_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            emission_factor_id = excluded.emission_factor_id,
            source_id = excluded.source_id,
            contributor_id = excluded.contributor_id,
            updated_at = excluded.updated_at,
            status = excluded.status
        """,
        (material_id, name, name_key, factor_id, source_id, contributor_id,
         now_iso(), now_iso(), "draft" if is_revision else "validated", material_rev_of),
    )
    return material_id


def upsert_liquid_factor(sqlite_path: str | Path, row: dict[str, Any]) -> str:
    with connect(sqlite_path) as conn:
        factor_id = upsert_liquid_factor_conn(conn, row)
        conn.commit()
        return factor_id


def upsert_liquid_factor_conn(conn: sqlite3.Connection, row: dict[str, Any]) -> str:
    name = clean_text(row.get("Produit"))
    if not name:
        raise ValueError("Nom du liquide / solvant manquant.")
    errs = quality_errors(check_liquid_factor(row))
    if errs:
        raise ValueError(format_issues(errs))
    name_key = normalize_key(name)
    code = normalize_nacres_prefix(row.get("Code NACRES"))
    canonical_id = stable_id("emission_factors", "liquid", name_key)
    factor_id, revision_of = _prepare_revision(conn, "emission_factors", canonical_id)
    contributor_id, source_id = contributor_and_source(conn, row)
    uncertainty = float_or_none(row.get("Incertitude (%)"))
    if uncertainty is not None and uncertainty > 1:
        uncertainty = uncertainty / 100.0
    conn.execute(
        """
        INSERT INTO emission_factors(
            id, name, name_key, factor_type, code_nacres, co2_factor, co2_unit,
            uncertainty, density_g_ml, concentration_mg_ml,
            source_id, contributor_id, created_at, updated_at, status, revision_of_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            code_nacres = excluded.code_nacres,
            co2_factor = excluded.co2_factor,
            uncertainty = excluded.uncertainty,
            density_g_ml = excluded.density_g_ml,
            concentration_mg_ml = excluded.concentration_mg_ml,
            source_id = excluded.source_id,
            contributor_id = excluded.contributor_id,
            updated_at = excluded.updated_at,
            status = excluded.status
        """,
        (
            factor_id,
            name,
            name_key,
            "liquid",
            code or None,
            float_or_none(row.get("Facteur CO₂ (kg CO₂e/kg)")),
            "kg CO2e/kg",
            uncertainty,
            float_or_none(row.get("Densité (g/mL)")),
            float_or_none(row.get("Concentration (mg/mL)")),
            source_id,
            contributor_id,
            text_or_none(row.get("date d'ajout")) or now_iso(),
            now_iso(),
            "draft" if revision_of else "validated",
            revision_of,
        ),
    )
    return factor_id


def upsert_commercial_product(
    sqlite_path: str | Path,
    row: dict[str, Any],
    *,
    existing_id: str | None = None,
) -> str:
    with connect(sqlite_path) as conn:
        product_id = upsert_commercial_product_conn(conn, row, existing_id=existing_id)
        conn.commit()
        return product_id


def upsert_commercial_product_conn(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    existing_id: str | None = None,
) -> str:
    name = clean_text(row.get("Consommable"))
    if not name:
        raise ValueError("Nom du consommable manquant.")
    errs = quality_errors(check_commercial_product(row))
    if errs:
        raise ValueError(format_issues(errs))
    code = normalize_nacres_prefix(row.get("Code NACRES"))
    reference = text_or_none(row.get("Référence"))
    canonical_id = existing_id or clean_text(row.get(SQLITE_ID_COL)) or find_existing_product_id(conn, row)
    if not canonical_id:
        canonical_id = stable_id("commercial_products", code, name, reference or "")

    # Révision si l'entrée canonique est déjà validée
    product_id, revision_of = _prepare_revision(conn, "commercial_products", canonical_id,
                                                 name_key_col=None)

    is_liquid = looks_like_liquid_commercial_product(row)
    product_type = "liquid" if is_liquid else "solid"
    volume_ml = float_or_none(row.get("Volume flacon (mL)"))
    sold_unit_volume_ml = volume_ml if is_liquid else None
    capacity_volume_ml = volume_ml if not is_liquid else None
    if is_liquid:
        factor_id = text_or_none(row.get("emission_factor_id")) or find_liquid_factor_id(
            conn, row.get("Facteur liquide source"), code
        )
    else:
        factor_id = None
    contributor_id, source_id = contributor_and_source(conn, row)
    catalogue_id = find_catalogue_id(conn, row.get("code_ijm"))
    status = "draft" if (revision_of or not clean_text(row.get("Source"))) else "validated"
    conn.execute(
        """
        INSERT INTO commercial_products(
            id, name, brand, reference, code_nacres, product_type,
            sold_packaging_label, units_per_sold_packaging, price_sold_packaging,
            sold_unit_volume_ml, capacity_volume_ml, emission_factor_id,
            ijm_catalogue_id, source_id, contributor_id, created_at, updated_at, status,
            revision_of_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            brand = excluded.brand,
            reference = excluded.reference,
            code_nacres = excluded.code_nacres,
            product_type = excluded.product_type,
            sold_packaging_label = excluded.sold_packaging_label,
            units_per_sold_packaging = excluded.units_per_sold_packaging,
            price_sold_packaging = excluded.price_sold_packaging,
            sold_unit_volume_ml = excluded.sold_unit_volume_ml,
            capacity_volume_ml = excluded.capacity_volume_ml,
            emission_factor_id = excluded.emission_factor_id,
            ijm_catalogue_id = excluded.ijm_catalogue_id,
            source_id = excluded.source_id,
            contributor_id = excluded.contributor_id,
            updated_at = excluded.updated_at,
            status = excluded.status
        """,
        (
            product_id,
            name,
            text_or_none(row.get("Marque")) or text_or_none(row.get("marque_ijm")),
            reference,
            code or None,
            product_type,
            text_or_none(row.get("condt_ijm")),
            int_or_none(row.get("Nbr par conditionnement")),
            float_or_none(row.get("Prix du conditionnement")),
            sold_unit_volume_ml,
            capacity_volume_ml,
            factor_id,
            catalogue_id,
            source_id,
            contributor_id,
            text_or_none(row.get("date d'ajout")) or now_iso(),
            now_iso(),
            status,
            revision_of,
        ),
    )
    replace_product_components(conn, product_id, row)
    return product_id


def find_existing_product_id(conn: sqlite3.Connection, row: dict[str, Any]) -> str | None:
    code = normalize_nacres_prefix(row.get("Code NACRES"))
    reference = clean_text(row.get("Référence"))
    name = clean_text(row.get("Consommable"))
    if code and reference:
        existing = conn.execute(
            """
            SELECT id FROM commercial_products
            WHERE code_nacres = ? AND reference = ?
            ORDER BY rowid LIMIT 1
            """,
            (code, reference),
        ).fetchone()
        if existing:
            return existing["id"]
    if code and name:
        existing = conn.execute(
            """
            SELECT id FROM commercial_products
            WHERE code_nacres = ? AND name = ?
            ORDER BY rowid LIMIT 1
            """,
            (code, name),
        ).fetchone()
        if existing:
            return existing["id"]
    return None


def find_catalogue_id(conn: sqlite3.Connection, code_ijm: Any) -> str | None:
    code = clean_text(code_ijm)
    if not code:
        return None
    row = conn.execute(
        "SELECT id FROM catalogue_ijm WHERE code_ijm = ? ORDER BY rowid LIMIT 1",
        (code,),
    ).fetchone()
    return row["id"] if row else None


def replace_product_components(conn: sqlite3.Connection, product_id: str, row: dict[str, Any]) -> None:
    conn.execute("DELETE FROM product_components WHERE product_id = ?", (product_id,))
    specs = [
        ("product", "Matériau consommable", "Masse unitaire (g)", 1),
        ("product", "Matériau deuxieme materiaux", "Masse unitaire deuxieme materiaux (g)", 1),
        ("product", "Matériau troisième materiaux", "Masse unitaire troisième materiaux (g)", 1),
        ("secondary_packaging", "Matériau emballage", "Masse emballage unitaire (g)", 1),
        (
            "primary_packaging",
            "Matériau conditionnement",
            "Masse condionnement (g)",
            int_or_none(row.get("Nbr par conditionnement")) or 1,
        ),
    ]
    for component_type, material_col, mass_col, units_divisor in specs:
        material_name = clean_text(row.get(material_col))
        mass_g = float_or_none(row.get(mass_col))
        if not material_name and mass_g is None:
            continue
        material_id = find_material_id(conn, material_name)
        component_id = stable_id(
            "product_components",
            product_id,
            component_type,
            material_col,
            material_name,
            mass_g,
        )
        conn.execute(
            """
            INSERT INTO product_components(
                id, product_id, component_type, material_id, mass_g, units_divisor
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (component_id, product_id, component_type, material_id, mass_g, units_divisor),
        )
