# SPDX-License-Identifier: GPL-3.0-or-later
"""Stockage SQLite intégré au schéma LABeCO2 pour le scraper fournisseur."""

from __future__ import annotations

import csv
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tools.supplier_scraper.parser import ProductCandidate
from ui.sqlite_schema import ensure_app_schema


_ZERO_UUID = uuid.UUID(int=0)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def stable_id(namespace: str, *parts: Any) -> str:
    key = "|".join(clean(part).casefold() for part in parts)
    return str(uuid.uuid5(_ZERO_UUID, f"{namespace}:{key}"))


@dataclass(frozen=True)
class UpsertResult:
    reference_id: str
    generic_product_id: str
    inserted: bool
    updated: bool


class SupplierStorage:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        ensure_app_schema(conn)
        return conn

    def start_run(
        self,
        conn: sqlite3.Connection,
        *,
        supplier: str,
        dry_run: bool,
        config_path: str,
        start_url_count: int,
    ) -> str:
        run_id = stable_id("supplier_scrape_runs", supplier, now_iso(), config_path)
        conn.execute(
            """
            INSERT INTO supplier_scrape_runs(
                id, supplier, started_at, status, dry_run, config_path, start_url_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, supplier, now_iso(), "running", int(dry_run), config_path, start_url_count),
        )
        return run_id

    def finish_run(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        *,
        status: str,
        request_count: int,
        stored_reference_count: int,
        notes: str = "",
    ) -> None:
        conn.execute(
            """
            UPDATE supplier_scrape_runs
            SET finished_at = ?, status = ?, request_count = ?,
                stored_reference_count = ?, notes = ?
            WHERE id = ?
            """,
            (now_iso(), status, request_count, stored_reference_count, notes, run_id),
        )

    def log_fetch(
        self,
        conn: sqlite3.Connection,
        *,
        run_id: str,
        supplier: str,
        url: str,
        status_code: int | None,
        from_cache: bool,
        html_hash: str = "",
        error: str = "",
        notes: str = "",
    ) -> None:
        conn.execute(
            """
            INSERT INTO supplier_fetch_log(
                id, run_id, supplier, url, fetched_at, status_code,
                from_cache, html_hash, error, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stable_id("supplier_fetch_log", run_id, url, now_iso()),
                run_id,
                supplier,
                url,
                now_iso(),
                status_code,
                int(from_cache),
                html_hash,
                error,
                notes,
            ),
        )

    def upsert_reference(
        self,
        conn: sqlite3.Connection,
        candidate: ProductCandidate,
    ) -> UpsertResult:
        generic_id = stable_id(
            "supplier_generic_products",
            candidate.product_name_short,
            candidate.generic_category,
        )
        reference_id = stable_id(
            "supplier_references",
            candidate.supplier,
            candidate.supplier_product_ref,
        )
        existing = conn.execute(
            "SELECT id FROM supplier_references WHERE supplier = ? AND supplier_product_ref = ?",
            (candidate.supplier, candidate.supplier_product_ref),
        ).fetchone()

        now = now_iso()
        conn.execute(
            """
            INSERT INTO supplier_generic_products(
                id, product_name_short, generic_category, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(product_name_short, generic_category) DO UPDATE SET
                updated_at = excluded.updated_at
            """,
            (
                generic_id,
                candidate.product_name_short,
                candidate.generic_category,
                now,
                now,
            ),
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
                candidate.supplier,
                candidate.supplier_product_ref,
                candidate.product_url,
                candidate.product_name_short,
                candidate.generic_category,
                candidate.packaging_text,
                int(candidate.price_publicly_visible),
                candidate.currency_detected,
                candidate.retrieval_date,
                candidate.source_html_hash,
                candidate.scraping_notes,
                now,
                now,
            ),
        )
        return UpsertResult(
            reference_id=reference_id,
            generic_product_id=generic_id,
            inserted=existing is None,
            updated=existing is not None,
        )

    def known_refs(self, conn: sqlite3.Connection, supplier: str) -> set[str]:
        return {
            row[0]
            for row in conn.execute(
                "SELECT supplier_product_ref FROM supplier_references WHERE supplier = ?",
                (supplier,),
            )
        }

    def export_references_csv(
        self,
        conn: sqlite3.Connection,
        path: str | Path,
        *,
        supplier: str = "",
    ) -> int:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        where = "WHERE supplier = ?" if supplier else ""
        params: Iterable[str] = (supplier,) if supplier else ()
        rows = conn.execute(
            f"""
            SELECT supplier, supplier_product_ref, product_url, product_name_short,
                   generic_category, packaging_text, price_publicly_visible,
                   currency_detected, retrieval_date, source_html_hash, scraping_notes
            FROM supplier_references
            {where}
            ORDER BY supplier, supplier_product_ref
            """,
            tuple(params),
        ).fetchall()
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "supplier",
                    "supplier_product_ref",
                    "product_url",
                    "product_name_short",
                    "generic_category",
                    "packaging_text",
                    "price_publicly_visible",
                    "currency_detected",
                    "retrieval_date",
                    "source_html_hash",
                    "scraping_notes",
                ]
            )
            for row in rows:
                writer.writerow([row[key] for key in row.keys()])
        return len(rows)


_CREATE_LOCAL_OBSERVATIONS = """
CREATE TABLE IF NOT EXISTS supplier_scrape_observations (
    id                       TEXT PRIMARY KEY,
    supplier                 TEXT NOT NULL,
    supplier_product_ref     TEXT NOT NULL,
    product_url              TEXT,
    product_name_short       TEXT,
    generic_category         TEXT,
    packaging_text           TEXT,
    price_publicly_visible   INTEGER NOT NULL DEFAULT 0,
    price_text               TEXT,
    price_value              REAL,
    currency_detected        TEXT,
    retrieval_date           TEXT NOT NULL,
    source_html_hash         TEXT,
    source_html_cache_path   TEXT,
    variant_refs_json        TEXT,
    variant_attributes_json  TEXT,
    scraping_notes           TEXT,
    created_at               TEXT NOT NULL,
    UNIQUE(supplier, supplier_product_ref, retrieval_date)
)
"""

_CREATE_LOCAL_PRICE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS supplier_local_price_snapshots (
    id                    TEXT PRIMARY KEY,
    observation_id        TEXT,
    supplier              TEXT NOT NULL,
    supplier_product_ref  TEXT NOT NULL,
    product_url           TEXT,
    price_text            TEXT,
    price_value           REAL,
    currency              TEXT,
    retrieved_at          TEXT NOT NULL,
    source_html_hash      TEXT,
    created_at            TEXT NOT NULL,
    FOREIGN KEY(observation_id) REFERENCES supplier_scrape_observations(id),
    UNIQUE(supplier, supplier_product_ref, retrieved_at, price_text)
)
"""


class LocalCaptureStorage:
    """SQLite privé pour observations larges non destinées à la base distribuée."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(_CREATE_LOCAL_OBSERVATIONS)
        conn.execute(_CREATE_LOCAL_PRICE_SNAPSHOTS)
        observation_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(supplier_scrape_observations)")
        }
        if "variant_attributes_json" not in observation_columns:
            conn.execute("ALTER TABLE supplier_scrape_observations ADD COLUMN variant_attributes_json TEXT")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_supplier_scrape_observations_ref
            ON supplier_scrape_observations(supplier, supplier_product_ref)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_supplier_local_price_snapshots_ref
            ON supplier_local_price_snapshots(supplier, supplier_product_ref)
            """
        )
        return conn

    def capture_candidate(
        self,
        conn: sqlite3.Connection,
        candidate: ProductCandidate,
        *,
        source_html_cache_path: str = "",
    ) -> str:
        now = now_iso()
        observation_id = stable_id(
            "supplier_scrape_observations",
            candidate.supplier,
            candidate.supplier_product_ref,
            candidate.retrieval_date,
        )
        conn.execute(
            """
            INSERT INTO supplier_scrape_observations(
                id, supplier, supplier_product_ref, product_url, product_name_short,
                generic_category, packaging_text, price_publicly_visible, price_text,
                price_value, currency_detected, retrieval_date, source_html_hash,
                source_html_cache_path, variant_refs_json, variant_attributes_json,
                scraping_notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(supplier, supplier_product_ref, retrieval_date) DO UPDATE SET
                product_url = excluded.product_url,
                product_name_short = excluded.product_name_short,
                generic_category = excluded.generic_category,
                packaging_text = excluded.packaging_text,
                price_publicly_visible = excluded.price_publicly_visible,
                price_text = excluded.price_text,
                price_value = excluded.price_value,
                currency_detected = excluded.currency_detected,
                source_html_hash = excluded.source_html_hash,
                source_html_cache_path = excluded.source_html_cache_path,
                variant_refs_json = excluded.variant_refs_json,
                variant_attributes_json = excluded.variant_attributes_json,
                scraping_notes = excluded.scraping_notes
            """,
            (
                observation_id,
                candidate.supplier,
                candidate.supplier_product_ref,
                candidate.product_url,
                candidate.product_name_short,
                candidate.generic_category,
                candidate.packaging_text,
                int(candidate.price_publicly_visible),
                candidate.price_text,
                candidate.price_value,
                candidate.currency_detected,
                candidate.retrieval_date,
                candidate.source_html_hash,
                source_html_cache_path,
                json.dumps(candidate.variant_refs, ensure_ascii=False),
                json.dumps(dict(candidate.variant_attributes), ensure_ascii=False),
                candidate.scraping_notes,
                now,
            ),
        )
        if candidate.price_publicly_visible:
            conn.execute(
                """
                INSERT INTO supplier_local_price_snapshots(
                    id, observation_id, supplier, supplier_product_ref, product_url,
                    price_text, price_value, currency, retrieved_at, source_html_hash,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(supplier, supplier_product_ref, retrieved_at, price_text)
                DO NOTHING
                """,
                (
                    stable_id(
                        "supplier_local_price_snapshots",
                        candidate.supplier,
                        candidate.supplier_product_ref,
                        candidate.retrieval_date,
                        candidate.price_text,
                    ),
                    observation_id,
                    candidate.supplier,
                    candidate.supplier_product_ref,
                    candidate.product_url,
                    candidate.price_text,
                    candidate.price_value,
                    candidate.currency_detected,
                    candidate.retrieval_date,
                    candidate.source_html_hash,
                    now,
                ),
            )
        return observation_id
