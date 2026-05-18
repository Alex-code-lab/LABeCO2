#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Migration LABeCO2 HDF5/CSV vers une base SQLite relationnelle."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ui.data_manager import DataManager
from ui.display_utils import (
    clean_text,
    looks_like_liquid_commercial_product,
    normalize_nacres_prefix,
)


UUID_NAMESPACE = uuid.UUID("f2a16a33-77cc-50cb-94df-0bc2d9dba04c")


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    checksum TEXT
);

CREATE TABLE contributors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    team TEXT,
    lab TEXT,
    email TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT,
    doi TEXT,
    citation TEXT,
    source_type TEXT,
    contributor_id TEXT REFERENCES contributors(id),
    created_at TEXT,
    updated_at TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    contribution_id TEXT,
    revision_of_id TEXT REFERENCES sources(id),
    validated_by_id TEXT REFERENCES contributors(id),
    validated_at TEXT,
    deprecated_at TEXT
);

CREATE TABLE nacres_codes (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    label TEXT,
    parent_code TEXT
);

CREATE TABLE purchase_factors (
    id TEXT PRIMARY KEY,
    category TEXT,
    subcategory TEXT,
    subsubcategory TEXT,
    unit TEXT,
    name TEXT,
    year INTEGER,
    total REAL,
    uncertainty REAL,
    raw_json TEXT
);

CREATE TABLE emission_factors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    factor_type TEXT,
    code_nacres TEXT,
    co2_factor REAL,
    co2_unit TEXT,
    uncertainty REAL,
    density_g_ml REAL,
    concentration_mg_ml REAL,
    source_id TEXT REFERENCES sources(id),
    contributor_id TEXT REFERENCES contributors(id),
    created_at TEXT,
    updated_at TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    contribution_id TEXT,
    revision_of_id TEXT REFERENCES emission_factors(id),
    validated_by_id TEXT REFERENCES contributors(id),
    validated_at TEXT,
    deprecated_at TEXT,
    UNIQUE(factor_type, name_key)
);

CREATE TABLE materials (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    emission_factor_id TEXT REFERENCES emission_factors(id),
    source_id TEXT REFERENCES sources(id),
    contributor_id TEXT REFERENCES contributors(id),
    created_at TEXT,
    updated_at TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    contribution_id TEXT,
    revision_of_id TEXT REFERENCES materials(id),
    validated_by_id TEXT REFERENCES contributors(id),
    validated_at TEXT,
    deprecated_at TEXT
);

CREATE TABLE catalogue_ijm (
    id TEXT PRIMARY KEY,
    code_ijm TEXT,
    designation TEXT,
    brand TEXT,
    conditionnement TEXT,
    price_ht REAL,
    units_per_pack INTEGER,
    source_catalogue TEXT,
    imported_at TEXT
);

CREATE TABLE commercial_products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    brand TEXT,
    reference TEXT,
    code_nacres TEXT,
    product_type TEXT NOT NULL CHECK(product_type IN ('solid', 'liquid')),
    sold_packaging_label TEXT,
    units_per_sold_packaging INTEGER,
    price_sold_packaging REAL,
    sold_unit_volume_ml REAL,
    capacity_volume_ml REAL,
    emission_factor_id TEXT REFERENCES emission_factors(id),
    ijm_catalogue_id TEXT REFERENCES catalogue_ijm(id),
    source_id TEXT REFERENCES sources(id),
    contributor_id TEXT REFERENCES contributors(id),
    created_at TEXT,
    updated_at TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    contribution_id TEXT,
    revision_of_id TEXT REFERENCES commercial_products(id),
    validated_by_id TEXT REFERENCES contributors(id),
    validated_at TEXT,
    deprecated_at TEXT,
    CHECK(NOT (sold_unit_volume_ml IS NOT NULL AND capacity_volume_ml IS NOT NULL))
);

CREATE TABLE product_components (
    id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES commercial_products(id),
    component_type TEXT NOT NULL,
    material_id TEXT REFERENCES materials(id),
    mass_g REAL,
    units_divisor INTEGER DEFAULT 1
);

CREATE TABLE transport_factors (
    id TEXT PRIMARY KEY,
    origin TEXT NOT NULL,
    distance_km REAL,
    mode TEXT,
    factor_kgco2e_per_kg REAL NOT NULL,
    uncertainty REAL,
    source_id TEXT REFERENCES sources(id),
    contributor_id TEXT REFERENCES contributors(id),
    created_at TEXT,
    updated_at TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    contribution_id TEXT,
    revision_of_id TEXT REFERENCES transport_factors(id),
    validated_by_id TEXT REFERENCES contributors(id),
    validated_at TEXT,
    deprecated_at TEXT
);

CREATE INDEX idx_purchase_factors_lookup
    ON purchase_factors(category, subcategory, subsubcategory, name, year);
CREATE INDEX idx_products_code_name ON commercial_products(code_nacres, name);
CREATE INDEX idx_components_product ON product_components(product_id);
CREATE INDEX idx_transport_origin ON transport_factors(origin);
"""


@dataclass
class MigrationReport:
    counts: dict[str, int] = field(default_factory=dict)
    unresolved_liquid_products: list[dict[str, str]] = field(default_factory=list)
    incomplete_components: list[dict[str, str]] = field(default_factory=list)
    unresolved_materials: list[dict[str, str]] = field(default_factory=list)
    suspected_duplicates: list[dict[str, str]] = field(default_factory=list)
    invalid_nacres_codes: list[dict[str, str]] = field(default_factory=list)
    negative_prices: list[dict[str, str]] = field(default_factory=list)

    def inc(self, key: str, amount: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + amount

    def as_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts,
            "unresolved_liquid_products": self.unresolved_liquid_products,
            "incomplete_components": self.incomplete_components,
            "unresolved_materials": self.unresolved_materials,
            "suspected_duplicates": self.suspected_duplicates,
            "invalid_nacres_codes": self.invalid_nacres_codes,
            "negative_prices": self.negative_prices,
        }

    def to_text(self) -> str:
        lines = ["Rapport de migration HDF5 -> SQLite", ""]
        for key in sorted(self.counts):
            lines.append(f"- {key} : {self.counts[key]}")
        sections = [
            ("Produits liquides sans facteur", self.unresolved_liquid_products),
            ("Composants incomplets", self.incomplete_components),
            ("Matériaux non résolus", self.unresolved_materials),
            ("Doublons suspects", self.suspected_duplicates),
            ("Codes NACRES invalides", self.invalid_nacres_codes),
            ("Prix négatifs", self.negative_prices),
        ]
        for title, rows in sections:
            lines.append("")
            lines.append(f"{title} : {len(rows)}")
            for row in rows[:50]:
                lines.append(f"  - {row}")
            if len(rows) > 50:
                lines.append(f"  ... {len(rows) - 50} autre(s)")
        return "\n".join(lines) + "\n"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(*parts: Any) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, "::".join(clean_text(p) for p in parts)))


def normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean_text(value))
    text = text.encode("ascii", "ignore").decode("ascii")
    return " ".join(text.casefold().split())


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


def record_json(row: pd.Series) -> str:
    data = {}
    for key, value in row.to_dict().items():
        value = nullable(value)
        data[key] = value.item() if hasattr(value, "item") else value
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def connect_sqlite(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT INTO schema_migrations(version, name, applied_at, checksum) VALUES (?, ?, ?, ?)",
        (1, "initial_hdf5_migration_schema", now_iso(), stable_id("schema", SCHEMA_SQL)),
    )


class MigrationContext:
    def __init__(self, conn: sqlite3.Connection, report: MigrationReport):
        self.conn = conn
        self.report = report
        self.contributors: dict[str, str] = {}
        self.sources: dict[str, str] = {}
        self.materials_by_key: dict[str, str] = {}
        self.liquid_factor_by_code_name: dict[tuple[str, str], str] = {}
        self.liquid_factor_by_name: dict[str, str] = {}
        self.catalogue_by_code: dict[str, str] = {}

        self.migration_contributor_id = self.ensure_contributor("migration")
        self.generic_source_id = self.ensure_source(
            "HDF5 import historique",
            contributor_id=self.migration_contributor_id,
            source_type="migration",
        )

    def ensure_contributor(self, name: Any) -> str:
        contributor_name = clean_text(name) or "migration"
        key = normalize_key(contributor_name)
        if key in self.contributors:
            return self.contributors[key]
        contributor_id = stable_id("contributors", key)
        self.conn.execute(
            """
            INSERT OR IGNORE INTO contributors(id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (contributor_id, contributor_name, now_iso(), now_iso()),
        )
        self.contributors[key] = contributor_id
        return contributor_id

    def ensure_source(
        self,
        title: Any,
        *,
        contributor_id: str | None = None,
        source_type: str = "autre",
    ) -> str:
        source_title = clean_text(title) or "HDF5 import historique"
        key = normalize_key(source_title)
        if key in self.sources:
            return self.sources[key]
        source_id = stable_id("sources", key)
        self.conn.execute(
            """
            INSERT OR IGNORE INTO sources(
                id, title, source_type, contributor_id, created_at, updated_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                source_title,
                source_type,
                contributor_id or self.migration_contributor_id,
                now_iso(),
                now_iso(),
                "validated",
            ),
        )
        self.sources[key] = source_id
        return source_id

    def source_from_row(self, row: pd.Series) -> str:
        source = clean_text(row.get("Source", ""))
        if not source:
            source = clean_text(row.get("Source catalogue IJM", ""))
        if not source:
            return self.generic_source_id
        return self.ensure_source(source, contributor_id=self.contributor_from_row(row))

    def contributor_from_row(self, row: pd.Series) -> str:
        return self.ensure_contributor(row.get("Signature", "") or row.get("Source/Signature", ""))


def migrate_purchase_factors(ctx: MigrationContext, main_df: pd.DataFrame) -> None:
    for index, row in main_df.iterrows():
        row_id = stable_id(
            "purchase_factors",
            index,
            row.get("category", ""),
            row.get("subcategory", ""),
            row.get("subsubcategory", ""),
            row.get("name", ""),
            row.get("year", ""),
        )
        ctx.conn.execute(
            """
            INSERT INTO purchase_factors(
                id, category, subcategory, subsubcategory, unit, name, year,
                total, uncertainty, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                text_or_none(row.get("category")),
                text_or_none(row.get("subcategory")),
                text_or_none(row.get("subsubcategory")),
                text_or_none(row.get("unit")),
                text_or_none(row.get("name")),
                int_or_none(row.get("year")),
                float_or_none(row.get("total")),
                float_or_none(row.get("uncertainty")),
                record_json(row),
            ),
        )
        ctx.report.inc("purchase_factors")


def migrate_nacres_codes(ctx: MigrationContext, *frames: pd.DataFrame) -> None:
    labels: dict[str, str] = {}
    for df in frames:
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            code = normalize_nacres_prefix(row.get("Code NACRES", row.get("subsubcategory", "")))
            if not code:
                continue
            label = clean_text(row.get("name", "")) or clean_text(row.get("Consommable", "")) or clean_text(row.get("Produit", ""))
            labels.setdefault(code, label)
    for code, label in sorted(labels.items()):
        ctx.conn.execute(
            "INSERT OR IGNORE INTO nacres_codes(id, code, label, parent_code) VALUES (?, ?, ?, ?)",
            (stable_id("nacres_codes", code), code, label or None, code[:2] if len(code) >= 2 else None),
        )
        ctx.report.inc("nacres_codes")


def migrate_liquid_factors(ctx: MigrationContext, df: pd.DataFrame, dm: DataManager) -> None:
    if df is None or df.empty:
        return
    for _, row in df.iterrows():
        name = clean_text(row.get("Produit", ""))
        if not name:
            continue
        code = normalize_nacres_prefix(row.get(dm.CODE_NACRES_COL, ""))
        if not code:
            ctx.report.invalid_nacres_codes.append({"table": "liquids", "name": name})
        factor_id = stable_id("emission_factors", "liquid", normalize_key(name))
        source_id = ctx.source_from_row(row)
        contributor_id = ctx.contributor_from_row(row)
        uncertainty = float_or_none(row.get("Incertitude (%)"))
        if uncertainty is not None and uncertainty > 1:
            uncertainty = uncertainty / 100.0
        ctx.conn.execute(
            """
            INSERT OR IGNORE INTO emission_factors(
                id, name, name_key, factor_type, code_nacres, co2_factor, co2_unit, uncertainty,
                density_g_ml, concentration_mg_ml, source_id, contributor_id,
                created_at, updated_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                factor_id,
                name,
                normalize_key(name),
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
                "validated",
            ),
        )
        ctx.liquid_factor_by_code_name[(code, normalize_key(name))] = factor_id
        ctx.liquid_factor_by_name.setdefault(normalize_key(name), factor_id)
        ctx.report.inc("liquid_emission_factors")


def migrate_materials(ctx: MigrationContext, df: pd.DataFrame, dm: DataManager) -> None:
    if df is None or df.empty:
        return
    for _, row in df.iterrows():
        name = clean_text(row.get(dm.MATERIAU_NAME_COL, ""))
        if not name:
            continue
        name_key = normalize_key(name)
        factor_id = stable_id("emission_factors", "material", name_key)
        material_id = stable_id("materials", name_key)
        source_id = ctx.source_from_row(row)
        contributor_id = ctx.contributor_from_row(row)
        ctx.conn.execute(
            """
            INSERT OR IGNORE INTO emission_factors(
                id, name, name_key, factor_type, code_nacres, co2_factor, co2_unit, uncertainty,
                source_id, contributor_id, created_at, updated_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                factor_id,
                name,
                name_key,
                "material",
                None,
                float_or_none(row.get(dm.EQUIV_CO2_COL)),
                "kg CO2e/kg",
                float_or_none(row.get(dm.UNCERTAINTY_COL)),
                source_id,
                contributor_id,
                now_iso(),
                now_iso(),
                "validated",
            ),
        )
        ctx.conn.execute(
            """
            INSERT OR IGNORE INTO materials(
                id, name, name_key, emission_factor_id, source_id, contributor_id,
                created_at, updated_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (material_id, name, name_key, factor_id, source_id, contributor_id, now_iso(), now_iso(), "validated"),
        )
        ctx.materials_by_key[name_key] = material_id
        ctx.report.inc("material_emission_factors")
        ctx.report.inc("materials")


def migrate_catalogue_ijm(ctx: MigrationContext, base_path: Path) -> None:
    path = base_path / "tools" / "scraping" / "output" / "prix_ijm_2025.csv"
    if not path.exists():
        return
    df = pd.read_csv(path, dtype=str)
    imported_at = now_iso()
    for index, row in df.iterrows():
        code_ijm = clean_text(row.get("code_ijm", ""))
        designation = clean_text(row.get("designation", ""))
        row_id = stable_id("catalogue_ijm", code_ijm, designation, row.get("condt", ""), index)
        ctx.conn.execute(
            """
            INSERT OR IGNORE INTO catalogue_ijm(
                id, code_ijm, designation, brand, conditionnement, price_ht,
                units_per_pack, source_catalogue, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                code_ijm or None,
                designation or None,
                text_or_none(row.get("marque")),
                text_or_none(row.get("condt")),
                float_or_none(row.get("prix_ht")),
                int_or_none(row.get("nb_unites")),
                "Catalogue IJM 2025",
                imported_at,
            ),
        )
        if code_ijm:
            ctx.catalogue_by_code.setdefault(code_ijm, row_id)
        ctx.report.inc("catalogue_ijm")


def find_liquid_factor_id(ctx: MigrationContext, code: str, factor_name: Any) -> str | None:
    name_key = normalize_key(factor_name)
    if not name_key:
        return None
    return (
        ctx.liquid_factor_by_code_name.get((code, name_key))
        or ctx.liquid_factor_by_name.get(name_key)
    )


def migrate_product_components(
    ctx: MigrationContext,
    product_id: str,
    row: pd.Series,
    dm: DataManager,
) -> None:
    specs = [
        ("product", dm.MATERIAU_COL, dm.MASSE_G_COL, 1),
        ("product", dm.MATERIAU2_COL, dm.MASSE_G2_COL, 1),
        ("product", dm.MATERIAU3_COL, dm.MASSE_G3_COL, 1),
        ("secondary_packaging", dm.MATERIAU_EMBALLAGE_COL, dm.MASSE_EMBALLAGE_COL, 1),
        ("primary_packaging", dm.MATERIAU_CONDITIONNEMENT_COL, dm.MASSE_CONDITIONNEMENT_COL, int_or_none(row.get(dm.NOMBRE_PAR_COND_COL)) or 1),
    ]
    for component_type, material_col, mass_col, units_divisor in specs:
        material_name = clean_text(row.get(material_col, ""))
        mass_g = float_or_none(row.get(mass_col))
        if not material_name and mass_g is None:
            continue
        material_id = ctx.materials_by_key.get(normalize_key(material_name))
        if material_name and material_id is None:
            ctx.report.unresolved_materials.append({
                "product": clean_text(row.get(dm.CONSOMMABLE_COL, "")),
                "material": material_name,
                "component_type": component_type,
            })
        if material_id is None or mass_g is None:
            ctx.report.incomplete_components.append({
                "product": clean_text(row.get(dm.CONSOMMABLE_COL, "")),
                "material": material_name,
                "mass_g": clean_text(row.get(mass_col, "")),
                "component_type": component_type,
            })
        component_id = stable_id("product_components", product_id, component_type, material_col, material_name, mass_g)
        ctx.conn.execute(
            """
            INSERT OR IGNORE INTO product_components(
                id, product_id, component_type, material_id, mass_g, units_divisor
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (component_id, product_id, component_type, material_id, mass_g, units_divisor),
        )
        ctx.report.inc("product_components")


def migrate_commercial_products(ctx: MigrationContext, df: pd.DataFrame, dm: DataManager) -> None:
    if df is None or df.empty:
        return

    seen: dict[tuple[str, str], int] = {}
    for index, row in df.iterrows():
        name = clean_text(row.get(dm.CONSOMMABLE_COL, ""))
        if not name:
            continue
        code = normalize_nacres_prefix(row.get(dm.CODE_NACRES_COL, ""))
        if not code:
            ctx.report.invalid_nacres_codes.append({"table": "commercial_products", "name": name})
        key = (code, normalize_key(name))
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            ctx.report.suspected_duplicates.append({"code_nacres": code, "name": name})

        product_id = stable_id("commercial_products", index, code, name, row.get("Référence", ""), row.get("code_ijm", ""))
        is_liquid = looks_like_liquid_commercial_product(row)
        product_type = "liquid" if is_liquid else "solid"
        volume_ml = float_or_none(row.get(dm.VOLUME_FLACON_COL))
        sold_unit_volume_ml = volume_ml if is_liquid else None
        capacity_volume_ml = volume_ml if not is_liquid else None
        factor_id = find_liquid_factor_id(ctx, code, row.get(dm.FACTEUR_LIQUIDE_SOURCE_COL, "")) if is_liquid else None
        if is_liquid:
            if factor_id:
                ctx.report.inc("liquid_products_linked_to_factor")
            else:
                ctx.report.unresolved_liquid_products.append({
                    "code_nacres": code,
                    "name": name,
                    "factor_source": clean_text(row.get(dm.FACTEUR_LIQUIDE_SOURCE_COL, "")),
                })

        price = float_or_none(row.get(dm.PRIX_CONDITIONNEMENT_COL))
        if price is not None and price < 0:
            ctx.report.negative_prices.append({"code_nacres": code, "name": name, "price": str(price)})

        ctx.conn.execute(
            """
            INSERT INTO commercial_products(
                id, name, brand, reference, code_nacres, product_type,
                sold_packaging_label, units_per_sold_packaging, price_sold_packaging,
                sold_unit_volume_ml, capacity_volume_ml, emission_factor_id,
                ijm_catalogue_id, source_id, contributor_id, created_at, updated_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                name,
                text_or_none(row.get("Marque")) or text_or_none(row.get(dm.MARQUE_IJM_COL)),
                text_or_none(row.get("Référence")),
                code or None,
                product_type,
                text_or_none(row.get(dm.CONDT_IJM_COL)),
                int_or_none(row.get(dm.NOMBRE_PAR_COND_COL)),
                price,
                sold_unit_volume_ml,
                capacity_volume_ml,
                factor_id,
                ctx.catalogue_by_code.get(clean_text(row.get(dm.CODE_IJM_COL, ""))),
                ctx.source_from_row(row),
                ctx.contributor_from_row(row),
                text_or_none(row.get("date d'ajout")) or now_iso(),
                now_iso(),
                "draft" if not clean_text(row.get("Source", "")) else "validated",
            ),
        )
        ctx.report.inc("commercial_products")
        ctx.report.inc("commercial_products_liquid" if is_liquid else "commercial_products_solid")
        migrate_product_components(ctx, product_id, row, dm)


def migrate_transport_factors(ctx: MigrationContext, df: pd.DataFrame, dm: DataManager) -> None:
    if df is None or df.empty:
        return
    for _, row in df.iterrows():
        origin = clean_text(row.get(dm.TRANSPORT_ORIGINE_COL, ""))
        if not origin:
            continue
        source_id = ctx.source_from_row(row)
        contributor_id = ctx.contributor_from_row(row)
        ctx.conn.execute(
            """
            INSERT OR IGNORE INTO transport_factors(
                id, origin, distance_km, mode, factor_kgco2e_per_kg,
                uncertainty, source_id, contributor_id, created_at, updated_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stable_id("transport_factors", normalize_key(origin)),
                origin,
                float_or_none(row.get("Distance (km)")),
                text_or_none(row.get("Mode")),
                float_or_none(row.get(dm.TRANSPORT_FACTOR_COL)) or 0.0,
                float_or_none(row.get(dm.TRANSPORT_UNCERT_COL)),
                source_id,
                contributor_id,
                now_iso(),
                now_iso(),
                "validated",
            ),
        )
        ctx.report.inc("transport_factors")


def migrate_project_to_sqlite(base_path: str | Path, output_path: str | Path) -> MigrationReport:
    base_path = Path(base_path)
    output_path = Path(output_path)
    if output_path.exists():
        output_path.unlink()

    dm = DataManager(str(base_path), user_path=str(base_path))
    report = MigrationReport()
    conn = connect_sqlite(output_path)
    try:
        create_schema(conn)
        ctx = MigrationContext(conn, report)
        migrate_purchase_factors(ctx, dm.get_main_data())
        migrate_catalogue_ijm(ctx, base_path)
        migrate_liquid_factors(ctx, dm.get_data_liquides(), dm)
        migrate_materials(ctx, dm.get_data_materials(), dm)
        migrate_commercial_products(ctx, dm.get_data_masse(), dm)
        migrate_transport_factors(ctx, dm.data_transport, dm)
        migrate_nacres_codes(
            ctx,
            dm.get_main_data(),
            dm.get_data_masse(),
            dm.get_data_liquides(),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return report


def write_report(report: MigrationReport, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_text(), encoding="utf-8")
    path.with_suffix(".json").write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-path", default=ROOT_DIR)
    parser.add_argument("--output", default="private/labeco2.sqlite")
    parser.add_argument("--report", default="private/migration_report.txt")
    args = parser.parse_args()

    report = migrate_project_to_sqlite(args.base_path, args.output)
    write_report(report, args.report)
    print(report.to_text())
    print(f"SQLite écrit dans : {args.output}")
    print(f"Rapport écrit dans : {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
