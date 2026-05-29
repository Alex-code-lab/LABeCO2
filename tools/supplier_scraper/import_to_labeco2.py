# SPDX-License-Identifier: GPL-3.0-or-later
"""Import contrôlé des observations privées de scraping vers la base LABeCO2.

La base de scraping reste une zone de staging privée. Ce script ne valide rien :
il crée des références fournisseurs, historise les prix observés, et prépare des
produits commerciaux en statut ``pending`` pour arbitrage dans ``lab_admin``.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.supplier_scraper.storage import stable_id  # noqa: E402
from ui.sqlite_schema import ensure_app_schema  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DB = PROJECT_ROOT / "private" / "supplier_scraping_lab.sqlite"
DEFAULT_TARGET_DB = PROJECT_ROOT / "private" / "labeco2.sqlite"

_INTEGER_RE = re.compile(r"\b(\d{1,6})\b")
_VOLUME_RE = re.compile(r"\b([\d,.]+)\s*(µl|ul|ml|l|litre?s?)\b", re.IGNORECASE)
_MASS_RE = re.compile(r"\b([\d,.]+)\s*(µg|ug|mg|g|kg)\b", re.IGNORECASE)
_FISHER_MARKETING_RE = re.compile(r"\s*Produit Greener Choice\b.*$", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class ScrapedObservation:
    supplier: str
    supplier_product_ref: str
    product_url: str
    product_name_short: str
    generic_category: str
    packaging_text: str
    price_publicly_visible: bool
    price_text: str
    price_value: float | None
    currency_detected: str
    retrieval_date: str
    source_html_hash: str
    variant_attributes_json: str
    scraping_notes: str


@dataclass
class ImportStats:
    observations: int = 0
    skipped_missing_ref: int = 0
    skipped_missing_name: int = 0
    supplier_references_inserted: int = 0
    supplier_references_updated: int = 0
    supplier_catalogue_inserted: int = 0
    supplier_catalogue_updated: int = 0
    price_snapshots_inserted: int = 0
    commercial_products_created_pending: int = 0
    commercial_products_existing: int = 0
    commercial_products_pending_updated: int = 0
    commercial_products_validated_untouched: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "observations": self.observations,
            "skipped_missing_ref": self.skipped_missing_ref,
            "skipped_missing_name": self.skipped_missing_name,
            "supplier_references_inserted": self.supplier_references_inserted,
            "supplier_references_updated": self.supplier_references_updated,
            "supplier_catalogue_inserted": self.supplier_catalogue_inserted,
            "supplier_catalogue_updated": self.supplier_catalogue_updated,
            "price_snapshots_inserted": self.price_snapshots_inserted,
            "commercial_products_created_pending": self.commercial_products_created_pending,
            "commercial_products_existing": self.commercial_products_existing,
            "commercial_products_pending_updated": self.commercial_products_pending_updated,
            "commercial_products_validated_untouched": self.commercial_products_validated_untouched,
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def parse_float(value: Any) -> float | None:
    text = clean(value).replace("\u202f", "").replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def stable_json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    import hashlib

    return hashlib.sha256(encoded).hexdigest()


def parse_units_per_pack(packaging_text: str) -> int | None:
    text = clean(packaging_text).replace("\u00a0", " ")
    if not text:
        return None
    match = _INTEGER_RE.search(text)
    if not match:
        return None
    return int(match.group(1))


def infer_mass_volume(packaging_text: str) -> tuple[float | None, float | None]:
    text = clean(packaging_text).replace(",", ".")
    mass_match = _MASS_RE.search(text)
    if mass_match:
        qty = parse_float(mass_match.group(1))
        unit = mass_match.group(2).lower()
        if qty is not None:
            factors = {"kg": 1000.0, "g": 1.0, "mg": 0.001, "ug": 0.000001, "µg": 0.000001}
            return qty * factors[unit], None
    volume_match = _VOLUME_RE.search(text)
    if volume_match:
        qty = parse_float(volume_match.group(1))
        unit = volume_match.group(2).lower()
        if qty is not None:
            factors = {"l": 1000.0, "litre": 1000.0, "litres": 1000.0, "ml": 1.0, "ul": 0.001, "µl": 0.001}
            return None, qty * factors[unit]
    return None, None


def infer_product_type(packaging_text: str, generic_category: str = "") -> str:
    text = f" {clean(packaging_text)} {clean(generic_category)} ".casefold()
    if _VOLUME_RE.search(text):
        return "liquid"
    return "solid"


def infer_brand(name: str, supplier: str) -> str:
    text = clean(name)
    if not text:
        return clean(supplier)
    if "fisherbrand" in text.casefold():
        return "Fisherbrand"
    if "vwr" in text.casefold():
        return "VWR"
    return text.split()[0].replace("™", "").strip(" -,:;") or clean(supplier)


def parse_json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(clean(text) or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def sanitize_product_name(name: str) -> str:
    text = clean(name)
    text = _FISHER_MARKETING_RE.sub("", text)
    text = text.replace('" />', "").replace("' />", "")
    return " ".join(text.split()).strip(" -,:;")


def product_display_name(obs: ScrapedObservation) -> str:
    base = sanitize_product_name(obs.product_name_short)
    attrs = parse_json_object(obs.variant_attributes_json)
    dimension = clean(
        attrs.get("Dimensions")
        or attrs.get("Dimension")
        or attrs.get("Taille")
        or attrs.get("Size")
    )
    if dimension and dimension.casefold() not in base.casefold():
        base = f"{base} - {dimension}"
    return base


def latest_observations(
    source_conn: sqlite3.Connection,
    *,
    supplier: str = "",
    limit: int | None = None,
) -> list[ScrapedObservation]:
    source_conn.row_factory = sqlite3.Row
    params: list[Any] = []
    where = ""
    if supplier:
        where = "WHERE lower(trim(o.supplier)) = lower(trim(?))"
        params.append(supplier)
    sql = f"""
        SELECT o.*
        FROM supplier_scrape_observations o
        JOIN (
            SELECT supplier, supplier_product_ref, MAX(retrieval_date) AS retrieval_date
            FROM supplier_scrape_observations
            {"WHERE lower(trim(supplier)) = lower(trim(?))" if supplier else ""}
            GROUP BY supplier, supplier_product_ref
        ) latest
          ON latest.supplier = o.supplier
         AND latest.supplier_product_ref = o.supplier_product_ref
         AND latest.retrieval_date = o.retrieval_date
        {where}
        ORDER BY o.supplier, o.supplier_product_ref
    """
    if supplier:
        params = [supplier, supplier]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    rows = source_conn.execute(sql, params).fetchall()
    return [
        ScrapedObservation(
            supplier=clean(row["supplier"]),
            supplier_product_ref=clean(row["supplier_product_ref"]),
            product_url=clean(row["product_url"]),
            product_name_short=clean(row["product_name_short"]),
            generic_category=clean(row["generic_category"]),
            packaging_text=clean(row["packaging_text"]),
            price_publicly_visible=bool(row["price_publicly_visible"]),
            price_text=clean(row["price_text"]),
            price_value=row["price_value"],
            currency_detected=clean(row["currency_detected"]),
            retrieval_date=clean(row["retrieval_date"]),
            source_html_hash=clean(row["source_html_hash"]),
            variant_attributes_json=clean(row["variant_attributes_json"]),
            scraping_notes=clean(row["scraping_notes"]),
        )
        for row in rows
    ]


def _commercial_product_by_ref(
    conn: sqlite3.Connection,
    *,
    supplier: str,
    supplier_product_ref: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT cp.*
        FROM commercial_products cp
        LEFT JOIN supplier_catalogue sc ON sc.id = cp.supplier_catalogue_id
        WHERE lower(trim(COALESCE(cp.reference, ''))) = lower(trim(?))
          AND (
              sc.supplier IS NULL
              OR lower(trim(sc.supplier)) = lower(trim(?))
              OR cp.supplier_catalogue_id IS NULL
          )
          AND COALESCE(cp.status, '') != 'deprecated'
        ORDER BY CASE cp.status WHEN 'validated' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END
        LIMIT 1
        """,
        (supplier_product_ref, supplier),
    ).fetchone()


def _upsert_supplier_reference(conn: sqlite3.Connection, obs: ScrapedObservation, now: str) -> tuple[bool, str]:
    display_name = product_display_name(obs)
    generic_id = stable_id("supplier_generic_products", display_name, obs.generic_category)
    reference_id = stable_id("supplier_references", obs.supplier, obs.supplier_product_ref)
    existing = conn.execute(
        "SELECT id FROM supplier_references WHERE supplier = ? AND supplier_product_ref = ?",
        (obs.supplier, obs.supplier_product_ref),
    ).fetchone()
    conn.execute(
        """
        INSERT INTO supplier_generic_products(
            id, product_name_short, generic_category, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(product_name_short, generic_category) DO UPDATE SET
            updated_at = excluded.updated_at
        """,
        (generic_id, display_name, obs.generic_category, now, now),
    )
    conn.execute(
        """
        INSERT INTO supplier_references(
            id, generic_product_id, supplier, supplier_product_ref, product_url,
            product_name_short, generic_category, packaging_text,
            price_publicly_visible, currency_detected, retrieval_date,
            source_html_hash, scraping_notes, first_seen_at, last_seen_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        ON CONFLICT(supplier, supplier_product_ref) DO UPDATE SET
            generic_product_id = excluded.generic_product_id,
            product_url = excluded.product_url,
            product_name_short = excluded.product_name_short,
            generic_category = excluded.generic_category,
            packaging_text = excluded.packaging_text,
            price_publicly_visible = excluded.price_publicly_visible,
            currency_detected = excluded.currency_detected,
            retrieval_date = excluded.retrieval_date,
            source_html_hash = excluded.source_html_hash,
            scraping_notes = excluded.scraping_notes,
            last_seen_at = excluded.last_seen_at,
            status = 'active'
        """,
        (
            reference_id,
            generic_id,
            obs.supplier,
            obs.supplier_product_ref,
            obs.product_url,
            display_name,
            obs.generic_category,
            obs.packaging_text,
            int(obs.price_publicly_visible),
            obs.currency_detected,
            obs.retrieval_date,
            obs.source_html_hash,
            obs.scraping_notes,
            now,
            now,
        ),
    )
    return existing is None, reference_id


def _upsert_supplier_catalogue(
    conn: sqlite3.Connection,
    obs: ScrapedObservation,
    *,
    batch_id: str,
    now: str,
) -> tuple[bool, str]:
    catalogue_id = stable_id("supplier_catalogue_scrape", obs.supplier, obs.supplier_product_ref)
    display_name = product_display_name(obs)
    mass_g, volume_ml = infer_mass_volume(obs.packaging_text)
    row_digest = stable_json_hash(
        {
            "supplier": obs.supplier,
            "supplier_product_ref": obs.supplier_product_ref,
            "product_url": obs.product_url,
            "product_name_short": display_name,
            "packaging_text": obs.packaging_text,
            "price_value": obs.price_value,
            "currency_detected": obs.currency_detected,
            "source_html_hash": obs.source_html_hash,
            "variant_attributes_json": obs.variant_attributes_json,
        }
    )
    existing = conn.execute("SELECT row_hash FROM supplier_catalogue WHERE id = ?", (catalogue_id,)).fetchone()
    conn.execute(
        """
        INSERT INTO supplier_catalogue(
            id, supplier, catalogue_date, code_fournisseur, designation,
            brand, conditionnement, price_ht, units_per_pack,
            mass_g, volume_ml, imported_at, import_batch_id, row_hash,
            product_url, source_html_hash, scraping_notes, variant_attributes_json,
            currency
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            catalogue_date = excluded.catalogue_date,
            designation = excluded.designation,
            brand = excluded.brand,
            conditionnement = excluded.conditionnement,
            price_ht = excluded.price_ht,
            units_per_pack = excluded.units_per_pack,
            mass_g = excluded.mass_g,
            volume_ml = excluded.volume_ml,
            imported_at = excluded.imported_at,
            import_batch_id = excluded.import_batch_id,
            row_hash = excluded.row_hash,
            product_url = excluded.product_url,
            source_html_hash = excluded.source_html_hash,
            scraping_notes = excluded.scraping_notes,
            variant_attributes_json = excluded.variant_attributes_json,
            currency = excluded.currency
        """,
        (
            catalogue_id,
            obs.supplier,
            obs.retrieval_date[:10],
            obs.supplier_product_ref,
            display_name,
            infer_brand(display_name, obs.supplier),
            obs.packaging_text,
            obs.price_value,
            parse_units_per_pack(obs.packaging_text),
            mass_g,
            volume_ml,
            now,
            batch_id,
            row_digest,
            obs.product_url,
            obs.source_html_hash,
            obs.scraping_notes,
            obs.variant_attributes_json,
            obs.currency_detected,
        ),
    )
    return existing is None, catalogue_id


def _insert_price_snapshot(conn: sqlite3.Connection, obs: ScrapedObservation) -> bool:
    if obs.price_value is None:
        return False
    price_id = stable_id(
        "supplier_price_cache",
        obs.supplier,
        obs.supplier_product_ref,
        obs.retrieval_date,
        obs.price_text,
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO supplier_price_cache(
            id, supplier, supplier_product_ref, product_url, price_value,
            currency, retrieved_at, source_html_hash, retrieval_context, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            price_id,
            obs.supplier,
            obs.supplier_product_ref,
            obs.product_url,
            obs.price_value,
            obs.currency_detected,
            obs.retrieval_date,
            obs.source_html_hash,
            "private_scrape_import",
            obs.price_text,
        ),
    )
    return conn.execute("SELECT changes()").fetchone()[0] > 0


def _create_pending_product(
    conn: sqlite3.Connection,
    obs: ScrapedObservation,
    *,
    catalogue_id: str,
    now: str,
) -> bool:
    product_id = stable_id("commercial_products_scrape", obs.supplier, obs.supplier_product_ref)
    mass_g, volume_ml = infer_mass_volume(obs.packaging_text)
    _ = mass_g
    display_name = product_display_name(obs)
    exists = conn.execute("SELECT 1 FROM commercial_products WHERE id = ?", (product_id,)).fetchone()
    if exists:
        return False
    conn.execute(
        """
        INSERT INTO commercial_products(
            id, name, brand, reference, code_nacres, product_type,
            sold_packaging_label, units_per_sold_packaging, price_sold_packaging,
            sold_unit_volume_ml, supplier_catalogue_id, status,
            created_at, updated_at, note
        ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
        """,
        (
            product_id,
            display_name or f"{obs.supplier} {obs.supplier_product_ref}",
            infer_brand(display_name, obs.supplier),
            obs.supplier_product_ref,
            infer_product_type(obs.packaging_text, obs.generic_category),
            obs.packaging_text,
            parse_units_per_pack(obs.packaging_text),
            obs.price_value,
            volume_ml,
            catalogue_id,
            now,
            now,
            "Import depuis scraping privé fournisseur. Vérifier NACRES, FE et cohérence avant validation.",
        ),
    )
    return True


def _update_pending_product(
    conn: sqlite3.Connection,
    obs: ScrapedObservation,
    *,
    product_id: str,
    catalogue_id: str,
    now: str,
) -> bool:
    _mass_g, volume_ml = infer_mass_volume(obs.packaging_text)
    display_name = product_display_name(obs)
    desired = {
        "name": display_name or f"{obs.supplier} {obs.supplier_product_ref}",
        "brand": infer_brand(display_name, obs.supplier),
        "product_type": infer_product_type(obs.packaging_text, obs.generic_category),
        "sold_packaging_label": obs.packaging_text,
        "units_per_sold_packaging": parse_units_per_pack(obs.packaging_text),
        "price_sold_packaging": obs.price_value,
        "sold_unit_volume_ml": volume_ml,
        "supplier_catalogue_id": catalogue_id,
    }
    current = conn.execute(
        """
        SELECT name, brand, product_type, sold_packaging_label,
               units_per_sold_packaging, price_sold_packaging,
               sold_unit_volume_ml, supplier_catalogue_id
        FROM commercial_products
        WHERE id = ?
        """,
        (product_id,),
    ).fetchone()
    if current and all(current[key] == value for key, value in desired.items()):
        return False
    conn.execute(
        """
        UPDATE commercial_products
        SET name = ?,
            brand = ?,
            product_type = ?,
            sold_packaging_label = ?,
            units_per_sold_packaging = ?,
            price_sold_packaging = ?,
            sold_unit_volume_ml = ?,
            supplier_catalogue_id = ?,
            updated_at = ?,
            note = COALESCE(note, ?)
        WHERE id = ?
          AND COALESCE(status, '') != 'validated'
          AND COALESCE(status, '') != 'deprecated'
        """,
        (
            desired["name"],
            desired["brand"],
            desired["product_type"],
            desired["sold_packaging_label"],
            desired["units_per_sold_packaging"],
            desired["price_sold_packaging"],
            desired["sold_unit_volume_ml"],
            desired["supplier_catalogue_id"],
            now,
            "Import depuis scraping privé fournisseur. Vérifier NACRES, FE et cohérence avant validation.",
            product_id,
        ),
    )
    return conn.execute("SELECT changes()").fetchone()[0] > 0


def import_observations(
    source_conn: sqlite3.Connection,
    target_conn: sqlite3.Connection,
    *,
    supplier: str = "",
    limit: int | None = None,
) -> ImportStats:
    ensure_app_schema(target_conn)
    target_conn.row_factory = sqlite3.Row
    observations = latest_observations(source_conn, supplier=supplier, limit=limit)
    now = now_iso()
    batch_id = str(uuid.uuid4())
    stats = ImportStats(observations=len(observations))

    target_conn.execute(
        """
        INSERT INTO admin_import_batches(
            id, import_type, file_path, supplier, catalogue_date,
            created_at, summary_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            "supplier_private_scrape",
            "",
            supplier,
            now[:10],
            now,
            "{}",
            "preview",
        ),
    )

    for obs in observations:
        if not obs.supplier_product_ref:
            stats.skipped_missing_ref += 1
            continue
        if not product_display_name(obs):
            stats.skipped_missing_name += 1
            continue

        inserted_ref, _reference_id = _upsert_supplier_reference(target_conn, obs, now)
        if inserted_ref:
            stats.supplier_references_inserted += 1
        else:
            stats.supplier_references_updated += 1

        inserted_catalogue, catalogue_id = _upsert_supplier_catalogue(
            target_conn,
            obs,
            batch_id=batch_id,
            now=now,
        )
        if inserted_catalogue:
            stats.supplier_catalogue_inserted += 1
        else:
            stats.supplier_catalogue_updated += 1

        if _insert_price_snapshot(target_conn, obs):
            stats.price_snapshots_inserted += 1

        existing_product = _commercial_product_by_ref(
            target_conn,
            supplier=obs.supplier,
            supplier_product_ref=obs.supplier_product_ref,
        )
        if existing_product:
            stats.commercial_products_existing += 1
            if clean(existing_product["status"]) == "validated":
                stats.commercial_products_validated_untouched += 1
            elif _update_pending_product(
                target_conn,
                obs,
                product_id=existing_product["id"],
                catalogue_id=catalogue_id,
                now=now,
            ):
                stats.commercial_products_pending_updated += 1
            continue

        if _create_pending_product(target_conn, obs, catalogue_id=catalogue_id, now=now):
            stats.commercial_products_created_pending += 1

    target_conn.execute(
        """
        UPDATE admin_import_batches
        SET summary_json = ?, status = ?
        WHERE id = ?
        """,
        (json.dumps(stats.as_dict(), ensure_ascii=False, sort_keys=True), "imported", batch_id),
    )
    return stats


def format_stats(stats: ImportStats, *, applied: bool) -> str:
    mode = "APPLIQUÉ" if applied else "APERÇU"
    lines = [
        f"Mode : {mode}",
        f"Observations privées lues : {stats.observations}",
        f"Références fournisseur ajoutées : {stats.supplier_references_inserted}",
        f"Références fournisseur mises à jour : {stats.supplier_references_updated}",
        f"Lignes catalogue ajoutées : {stats.supplier_catalogue_inserted}",
        f"Lignes catalogue mises à jour : {stats.supplier_catalogue_updated}",
        f"Prix historisés ajoutés : {stats.price_snapshots_inserted}",
        f"Produits LABeCO2 créés en attente : {stats.commercial_products_created_pending}",
        f"Produits déjà présents : {stats.commercial_products_existing}",
        f"Produits non validés mis à jour : {stats.commercial_products_pending_updated}",
        f"Produits validés laissés intacts : {stats.commercial_products_validated_untouched}",
    ]
    if stats.skipped_missing_ref or stats.skipped_missing_name:
        lines.append(f"Lignes ignorées sans référence : {stats.skipped_missing_ref}")
        lines.append(f"Lignes ignorées sans nom : {stats.skipped_missing_name}")
    return "\n".join(lines)


def backup_database(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.backup_before_supplier_import_{timestamp}")
    shutil.copy2(path, backup)
    return backup


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Importe les observations privées de scraping dans la base LABeCO2.",
    )
    parser.add_argument("--source-db", default=str(DEFAULT_SOURCE_DB), help="Base SQLite privée du scraper.")
    parser.add_argument("--target-db", default=str(DEFAULT_TARGET_DB), help="Base SQLite LABeCO2 cible.")
    parser.add_argument("--supplier", default="", help="Limiter à un fournisseur.")
    parser.add_argument("--limit", type=int, default=None, help="Limiter le nombre de références importées.")
    parser.add_argument("--apply", action="store_true", help="Écrit réellement dans la base cible.")
    parser.add_argument("--no-backup", action="store_true", help="Ne crée pas de sauvegarde avant --apply.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_db = Path(args.source_db)
    target_db = Path(args.target_db)
    if not source_db.exists():
        print(f"Base source introuvable : {source_db}", file=sys.stderr)
        return 2
    if not target_db.exists():
        print(f"Base cible introuvable : {target_db}", file=sys.stderr)
        return 2

    backup_path: Path | None = None
    if args.apply and not args.no_backup:
        backup_path = backup_database(target_db)

    source_conn = sqlite3.connect(source_db)
    target_conn = sqlite3.connect(target_db)
    try:
        stats = import_observations(
            source_conn,
            target_conn,
            supplier=args.supplier,
            limit=args.limit,
        )
        if args.apply:
            target_conn.commit()
        else:
            target_conn.rollback()
        print(format_stats(stats, applied=args.apply))
        if backup_path:
            print(f"Sauvegarde créée : {backup_path}")
    except Exception:
        target_conn.rollback()
        raise
    finally:
        source_conn.close()
        target_conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
