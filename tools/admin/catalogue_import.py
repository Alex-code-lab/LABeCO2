# SPDX-License-Identifier: GPL-3.0-or-later
"""Prévisualisation et import contrôlé des catalogues fournisseurs."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ui.sqlite_schema import ensure_app_schema


_ZERO_UUID = uuid.UUID(int=0)
_UNIT_RE = re.compile(
    r"([\d,\.]+)\s*(kg|mg|g\b|litre?s?|l\b|ml|µl|ug|µg|iu|u\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CatalogueInputRow:
    row_number: int
    supplier: str
    catalogue_date: str
    code_fournisseur: str
    designation: str
    brand: str
    conditionnement: str
    price_ht: float | None
    units_per_pack: int
    code_nacres: str


@dataclass
class CataloguePreviewItem:
    row: CatalogueInputRow
    action: str
    reason: str
    supplier_catalogue_id: str = ""
    product_id: str = ""
    existing_product_id: str = ""
    price_changed: bool = False
    packaging_changed: bool = False
    ignored: bool = False


@dataclass
class CataloguePreview:
    path: Path
    supplier: str
    catalogue_date: str
    items: list[CataloguePreviewItem] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        counts = {
            "new_products": 0,
            "linked_existing": 0,
            "existing_catalogue": 0,
            "price_changed": 0,
            "packaging_changed": 0,
            "ambiguous": 0,
            "ignored": 0,
        }
        for item in self.items:
            if item.action in counts:
                counts[item.action] += 1
            if item.price_changed:
                counts["price_changed"] += 1
            if item.packaging_changed:
                counts["packaging_changed"] += 1
            if item.ignored:
                counts["ignored"] += 1
        return counts

    @property
    def importable_items(self) -> list[CataloguePreviewItem]:
        return [
            item for item in self.items
            if not item.ignored and item.action in {"new_products", "linked_existing", "existing_catalogue"}
        ]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_uuid(namespace: str, *parts: Any) -> str:
    key = "|".join("" if part is None else str(part) for part in parts)
    return str(uuid.uuid5(_ZERO_UUID, f"{namespace}:{key}"))


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "n/a"} else text


def parse_float(value: Any) -> float | None:
    text = clean(value).replace("\u202f", "").replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if number == number else None


def parse_int(value: Any, default: int = 1) -> int:
    number = parse_float(value)
    if number is None:
        return default
    try:
        return int(number)
    except (TypeError, ValueError):
        return default


def infer_mass_volume(conditionnement: str) -> tuple[float | None, float | None]:
    match = _UNIT_RE.search(clean(conditionnement))
    if not match:
        return None, None
    qty = parse_float(match.group(1))
    if qty is None:
        return None, None
    unit = match.group(2).lower()
    if unit == "kg":
        return qty * 1000, None
    if unit == "g":
        return qty, None
    if unit == "mg":
        return qty / 1000, None
    if unit in {"µg", "ug"}:
        return qty / 1_000_000, None
    if unit in {"l", "litre", "litres"}:
        return None, qty * 1000
    if unit == "ml":
        return None, qty
    if unit == "µl":
        return None, qty / 1000
    return None, None


def infer_product_type(conditionnement: str) -> str:
    lower = f" {clean(conditionnement).lower()} "
    if any(token in lower for token in (" ml", " µl", " litre", " liter", " l ")):
        return "liquid"
    return "solid"


def row_hash(row: CatalogueInputRow) -> str:
    payload = {
        "supplier": row.supplier,
        "catalogue_date": row.catalogue_date,
        "code_fournisseur": row.code_fournisseur,
        "designation": row.designation,
        "brand": row.brand,
        "conditionnement": row.conditionnement,
        "price_ht": row.price_ht,
        "units_per_pack": row.units_per_pack,
        "code_nacres": row.code_nacres,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        import pandas as pd

        df = pd.read_excel(path, dtype=str)
        return df.fillna("").to_dict(orient="records")

    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


_ALIASES = {
    "supplier": ("fournisseur", "supplier"),
    "catalogue_date": ("catalogue_date", "date_catalogue", "version", "annee", "année"),
    "code_fournisseur": ("code_fournisseur", "reference", "référence", "ref", "code catalogue", "code_catalogue"),
    "designation": ("designation", "désignation", "name", "nom", "produit"),
    "brand": ("marque", "brand"),
    "conditionnement": ("condt", "conditionnement", "packaging"),
    "price_ht": ("prix_ht", "price_ht", "prix", "prix ht", "prix (€)", "prix_eur"),
    "units_per_pack": ("nb_unites", "units_per_pack", "unités", "unites", "nombre_unites"),
    "code_nacres": ("code_nacres", "nacres", "code nacres"),
}


def _value(raw: dict[str, Any], logical_name: str) -> Any:
    normalized = {clean(key).lower(): value for key, value in raw.items()}
    for alias in _ALIASES[logical_name]:
        if alias.lower() in normalized:
            return normalized[alias.lower()]
    return ""


def load_catalogue_rows(
    path: Path,
    *,
    supplier_override: str = "",
    catalogue_date_override: str = "",
) -> list[CatalogueInputRow]:
    rows: list[CatalogueInputRow] = []
    for idx, raw in enumerate(_read_rows(path), start=2):
        supplier = clean(supplier_override) or clean(_value(raw, "supplier"))
        catalogue_date = clean(catalogue_date_override) or clean(_value(raw, "catalogue_date"))
        row = CatalogueInputRow(
            row_number=idx,
            supplier=supplier,
            catalogue_date=catalogue_date,
            code_fournisseur=clean(_value(raw, "code_fournisseur")),
            designation=clean(_value(raw, "designation")),
            brand=clean(_value(raw, "brand")),
            conditionnement=clean(_value(raw, "conditionnement")),
            price_ht=parse_float(_value(raw, "price_ht")),
            units_per_pack=parse_int(_value(raw, "units_per_pack")),
            code_nacres=clean(_value(raw, "code_nacres")).upper(),
        )
        rows.append(row)
    return rows


def _supplier_catalogue_id(row: CatalogueInputRow) -> str:
    return stable_uuid("supplier_catalogue", row.supplier, row.catalogue_date, row.code_fournisseur)


def _commercial_product_id(row: CatalogueInputRow) -> str:
    return stable_uuid("commercial_products", row.supplier, row.code_fournisseur)


def _existing_supplier_catalogue(conn: sqlite3.Connection, row: CatalogueInputRow) -> dict | None:
    conn.row_factory = sqlite3.Row
    found = conn.execute(
        """
        SELECT *
        FROM supplier_catalogue
        WHERE lower(trim(supplier)) = lower(trim(?))
          AND COALESCE(catalogue_date, '') = COALESCE(?, '')
          AND lower(trim(code_fournisseur)) = lower(trim(?))
        LIMIT 1
        """,
        (row.supplier, row.catalogue_date, row.code_fournisseur),
    ).fetchone()
    return dict(found) if found else None


def _existing_products(conn: sqlite3.Connection, row: CatalogueInputRow) -> list[dict]:
    conn.row_factory = sqlite3.Row
    exact = [
        dict(found) for found in conn.execute(
            """
            SELECT cp.*, sc.supplier AS linked_supplier
            FROM commercial_products cp
            LEFT JOIN supplier_catalogue sc ON sc.id = cp.supplier_catalogue_id
            WHERE lower(trim(cp.reference)) = lower(trim(?))
              AND (sc.supplier IS NULL OR lower(trim(sc.supplier)) = lower(trim(?)))
              AND cp.status != 'deprecated'
            ORDER BY CASE cp.status WHEN 'validated' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END
            """,
            (row.code_fournisseur, row.supplier),
        )
    ]
    if exact:
        return exact

    if not row.designation:
        return []
    return [
        dict(found) for found in conn.execute(
            """
            SELECT cp.*, sc.supplier AS linked_supplier
            FROM commercial_products cp
            LEFT JOIN supplier_catalogue sc ON sc.id = cp.supplier_catalogue_id
            WHERE lower(trim(COALESCE(cp.brand, ''))) = lower(trim(?))
              AND lower(trim(cp.name)) = lower(trim(?))
              AND lower(trim(COALESCE(cp.sold_packaging_label, ''))) = lower(trim(?))
              AND cp.status != 'deprecated'
            ORDER BY CASE cp.status WHEN 'validated' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END
            """,
            (row.brand, row.designation, row.conditionnement),
        )
    ]


def preview_catalogue_import(
    conn: sqlite3.Connection,
    path: Path,
    *,
    supplier_override: str = "",
    catalogue_date_override: str = "",
) -> CataloguePreview:
    ensure_app_schema(conn)
    rows = load_catalogue_rows(
        path,
        supplier_override=supplier_override,
        catalogue_date_override=catalogue_date_override,
    )
    supplier = clean(supplier_override) or next((row.supplier for row in rows if row.supplier), "")
    catalogue_date = clean(catalogue_date_override) or next((row.catalogue_date for row in rows if row.catalogue_date), "")
    preview = CataloguePreview(path=path, supplier=supplier, catalogue_date=catalogue_date)

    for row in rows:
        sc_id = _supplier_catalogue_id(row)
        product_id = _commercial_product_id(row)
        if not row.supplier or not row.code_fournisseur:
            preview.items.append(CataloguePreviewItem(
                row=row,
                action="ignored",
                reason="Fournisseur ou référence catalogue manquant.",
                supplier_catalogue_id=sc_id,
                product_id=product_id,
                ignored=True,
            ))
            continue

        catalogue = _existing_supplier_catalogue(conn, row)
        products = _existing_products(conn, row)
        if len(products) > 1:
            preview.items.append(CataloguePreviewItem(
                row=row,
                action="ambiguous",
                reason=f"{len(products)} produits existants correspondent.",
                supplier_catalogue_id=sc_id,
                product_id=product_id,
                existing_product_id=", ".join(product["id"] for product in products),
                ignored=True,
            ))
            continue

        existing_product = products[0] if products else None
        if existing_product:
            old_price = existing_product.get("price_sold_packaging")
            old_packaging = clean(existing_product.get("sold_packaging_label"))
            price_changed = (
                row.price_ht is not None
                and old_price is not None
                and abs(float(old_price) - float(row.price_ht)) > 1e-9
            )
            packaging_changed = bool(row.conditionnement and old_packaging and row.conditionnement != old_packaging)
            preview.items.append(CataloguePreviewItem(
                row=row,
                action="existing_catalogue" if catalogue else "linked_existing",
                reason="Produit existant lié au catalogue; aucune donnée validée ne sera écrasée.",
                supplier_catalogue_id=sc_id,
                product_id=existing_product["id"],
                existing_product_id=existing_product["id"],
                price_changed=price_changed,
                packaging_changed=packaging_changed,
            ))
            continue

        preview.items.append(CataloguePreviewItem(
            row=row,
            action="existing_catalogue" if catalogue else "new_products",
            reason="Nouvelle référence fournisseur; création en attente.",
            supplier_catalogue_id=sc_id,
            product_id=product_id,
        ))

    return preview


def apply_catalogue_import(conn: sqlite3.Connection, preview: CataloguePreview) -> dict[str, int]:
    ensure_app_schema(conn)
    now = now_iso()
    batch_id = str(uuid.uuid4())
    summary = preview.summary
    conn.execute(
        """
        INSERT INTO admin_import_batches(
            id, import_type, file_path, supplier, catalogue_date,
            created_at, summary_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            "supplier_catalogue",
            str(preview.path),
            preview.supplier,
            preview.catalogue_date,
            now,
            json.dumps(summary, ensure_ascii=False, sort_keys=True),
            "imported",
        ),
    )

    stats = dict(summary)
    stats.update({"inserted_catalogue": 0, "created_pending": 0, "linked": 0})

    for item in preview.importable_items:
        row = item.row
        mass_g, volume_ml = infer_mass_volume(row.conditionnement)
        product_type = infer_product_type(row.conditionnement)
        row_digest = row_hash(row)
        conn.execute(
            """
            INSERT OR IGNORE INTO supplier_catalogue(
                id, supplier, catalogue_date, code_fournisseur, designation,
                brand, conditionnement, price_ht, units_per_pack,
                mass_g, volume_ml, imported_at, import_batch_id, row_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.supplier_catalogue_id,
                row.supplier,
                row.catalogue_date,
                row.code_fournisseur,
                row.designation,
                row.brand,
                row.conditionnement,
                row.price_ht,
                row.units_per_pack,
                mass_g,
                volume_ml,
                now,
                batch_id,
                row_digest,
            ),
        )
        if conn.execute("SELECT changes()").fetchone()[0]:
            stats["inserted_catalogue"] += 1

        if item.existing_product_id:
            conn.execute(
                """
                UPDATE commercial_products
                SET supplier_catalogue_id = ?, updated_at = ?
                WHERE id = ? AND supplier_catalogue_id IS NULL
                """,
                (item.supplier_catalogue_id, now, item.existing_product_id),
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                stats["linked"] += 1
            continue

        exists = conn.execute(
            "SELECT 1 FROM commercial_products WHERE id = ? LIMIT 1",
            (item.product_id,),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """
            INSERT INTO commercial_products(
                id, name, brand, reference, code_nacres, product_type,
                sold_packaging_label, units_per_sold_packaging, price_sold_packaging,
                sold_unit_volume_ml, supplier_catalogue_id, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.product_id,
                row.designation or f"{row.supplier} {row.code_fournisseur}",
                row.brand,
                row.code_fournisseur,
                row.code_nacres or None,
                product_type,
                row.conditionnement,
                row.units_per_pack,
                row.price_ht,
                volume_ml,
                item.supplier_catalogue_id,
                "pending",
                now,
                now,
            ),
        )
        stats["created_pending"] += 1

    return stats


def format_preview_summary(preview: CataloguePreview) -> str:
    summary = preview.summary
    return (
        f"Fichier : {preview.path.name}\n"
        f"Fournisseur : {preview.supplier or 'non renseigné'}\n"
        f"Version/date catalogue : {preview.catalogue_date or 'non renseignée'}\n\n"
        f"Nouveaux produits en attente : {summary['new_products']}\n"
        f"Produits existants à lier : {summary['linked_existing']}\n"
        f"Lignes catalogue déjà connues : {summary['existing_catalogue']}\n"
        f"Prix changés détectés : {summary['price_changed']}\n"
        f"Conditionnements changés détectés : {summary['packaging_changed']}\n"
        f"Références ambiguës : {summary['ambiguous']}\n"
        f"Lignes ignorées : {summary['ignored']}"
    )
