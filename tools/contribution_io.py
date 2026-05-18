# SPDX-License-Identifier: GPL-3.0-or-later
"""Fonctions communes pour exporter et importer les contributions LABeCO2."""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


METIER_TABLES = ["emission_factors", "materials", "commercial_products", "transport_factors"]

TABLES_ORDER = [
    "contributors",
    "sources",
    "emission_factors",
    "materials",
    "commercial_products",
    "product_components",
    "transport_factors",
]

# Colonnes techniques peu utiles dans les diffs administrateur/CLI.
_SKIP_DIFF_COLS = {
    "name_key",
    "contribution_id",
    "revision_of_id",
    "validated_by_id",
    "validated_at",
    "deprecated_at",
    "created_at",
    "updated_at",
}

Logger = Callable[[str], None] | None


@dataclass
class ImportStats:
    new: int = 0
    updated: int = 0
    skipped: int = 0
    dependencies: int = 0

    def add(self, result: str) -> None:
        if result == "new":
            self.new += 1
        elif result == "updated":
            self.updated += 1
        else:
            self.skipped += 1


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(logger: Logger, message: str) -> None:
    if logger is not None:
        logger(message)


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def fetch_all(conn: sqlite3.Connection, sql: str, params=()) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [row_to_dict(r) for r in conn.execute(sql, params)]


def fetch_by_id(conn: sqlite3.Connection, table: str, row_id: str) -> dict | None:
    conn.row_factory = sqlite3.Row
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    return dict(row) if row else None


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def resolve_contributor(conn: sqlite3.Connection, selector: str | None) -> dict | None:
    if not selector:
        return None
    rows = fetch_all(
        conn,
        "SELECT * FROM contributors WHERE id = ? OR name LIKE ?",
        (selector, f"%{selector}%"),
    )
    if not rows:
        print(f"[WARN] Contributeur introuvable : {selector!r}", file=sys.stderr)
        return None
    if len(rows) > 1:
        print(f"[WARN] Plusieurs contributeurs correspondent à {selector!r} :", file=sys.stderr)
        for r in rows:
            print(f"  {r['id']}  {r['name']}", file=sys.stderr)
        print("Utilisez l'UUID exact pour lever l'ambiguïté.", file=sys.stderr)
        return None
    return rows[0]


def build_contributor_filter(contributor: dict | None) -> tuple[str, list]:
    if contributor is None:
        return "", []
    return " AND contributor_id = ?", [contributor["id"]]


def export_table(
    conn: sqlite3.Connection,
    table: str,
    extra_filter: str,
    params: list,
    status_filter: str,
) -> list[dict]:
    sql = f"SELECT * FROM {table} WHERE status {status_filter}{extra_filter} ORDER BY created_at"
    return fetch_all(conn, sql, params)


def collect_dependencies(
    conn: sqlite3.Connection, entries: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Retourne (sources, contributors) référencés par les entrées."""
    source_ids = set()
    contributor_ids = set()
    for entry in entries:
        data = entry["data"]
        if data.get("source_id"):
            source_ids.add(data["source_id"])
        if data.get("contributor_id"):
            contributor_ids.add(data["contributor_id"])
        if data.get("validated_by_id"):
            contributor_ids.add(data["validated_by_id"])

    sources = []
    for sid in sorted(source_ids):
        rows = fetch_all(conn, "SELECT * FROM sources WHERE id = ?", (sid,))
        if rows:
            sources.append(rows[0])
            if rows[0].get("contributor_id"):
                contributor_ids.add(rows[0]["contributor_id"])

    contributors = []
    for cid in sorted(contributor_ids):
        rows = fetch_all(conn, "SELECT * FROM contributors WHERE id = ?", (cid,))
        if rows:
            contributors.append(rows[0])

    return sources, contributors


def collect_product_components(conn: sqlite3.Connection, product_ids: list[str]) -> list[dict]:
    if not product_ids:
        return []
    placeholders = ",".join("?" * len(product_ids))
    return fetch_all(
        conn,
        f"SELECT * FROM product_components WHERE product_id IN ({placeholders}) ORDER BY rowid",
        product_ids,
    )


def build_contribution_payload(
    conn: sqlite3.Connection,
    *,
    contributor_selector: str | None = None,
    tables: list[str] | None = None,
    include_validated: bool = False,
) -> tuple[dict, dict | None]:
    tables_to_export = tables or METIER_TABLES
    unknown = [table for table in tables_to_export if table not in METIER_TABLES]
    if unknown:
        raise ValueError(f"Tables inconnues : {unknown}. Valeurs possibles : {METIER_TABLES}")

    contributor = resolve_contributor(conn, contributor_selector)
    extra_filter, filter_params = build_contributor_filter(contributor)
    status_filter = "IN ('draft', 'validated')" if include_validated else "= 'draft'"

    all_entries: list[dict] = []
    component_entries: list[dict] = []

    for table in tables_to_export:
        rows = export_table(conn, table, extra_filter, filter_params, status_filter)
        for row in rows:
            all_entries.append({"table": table, "id": row["id"], "data": row})

        if table == "commercial_products" and rows:
            product_ids = [r["id"] for r in rows]
            components = collect_product_components(conn, product_ids)
            for comp in components:
                component_entries.append({
                    "table": "product_components",
                    "id": comp["id"],
                    "data": comp,
                })

    all_entries.extend(component_entries)
    sources, contributors = collect_dependencies(conn, all_entries)

    payload = {
        "format_version": "1",
        "exported_at": now_iso(),
        "contributor": contributor,
        "sources": sources,
        "contributors": contributors,
        "entries": all_entries,
    }
    return payload, contributor


def default_contribution_path(contributor: dict | None) -> str:
    contributor_name = (contributor or {}).get("name", "inconnu")
    date_slug = datetime.now().strftime("%Y-%m-%d")
    safe_name = contributor_name.replace(" ", "_").replace("/", "_")
    return f"contribution_LABeCO2_{date_slug}_{safe_name}.json"


def write_contribution_payload(payload: dict, output_path: str | Path) -> None:
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)


def load_contribution_payload(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    validate_contribution_payload(payload)
    return payload


def validate_contribution_payload(payload: dict) -> None:
    fmt = payload.get("format_version")
    if fmt != "1":
        raise ValueError(f"Format de contribution non supporté : {fmt!r}")


def diff_rows(old: dict, new: dict) -> list[str]:
    lines = []
    all_keys = sorted(set(old) | set(new))
    for key in all_keys:
        if key in _SKIP_DIFF_COLS:
            continue
        old_value = old.get(key)
        new_value = new.get(key)
        if old_value != new_value:
            lines.append(f"  {key}: {old_value!r}  ->  {new_value!r}")
    return lines


def row_label(data: dict) -> str:
    return data.get("name") or data.get("title") or data.get("origin") or ""


def upsert_row(
    conn: sqlite3.Connection,
    table: str,
    data: dict,
    validate: bool,
    dry_run: bool,
    logger: Logger = print,
) -> str:
    """Insère ou met à jour une ligne. Retourne 'new', 'updated', ou 'skipped'."""
    row_id = data.get("id")
    existing = fetch_by_id(conn, table, row_id) if row_id else None
    cols = table_columns(conn, table)

    values = {column: data.get(column) for column in cols if column in data}
    if "updated_at" in cols:
        values["updated_at"] = now_iso()
    if validate and "status" in cols:
        values["status"] = "validated"
        values["validated_at"] = now_iso()

    if existing is None:
        _log(logger, f"  + NEW [{table}] {row_id}  {row_label(data)}")
        if not dry_run:
            placeholders = ", ".join("?" * len(values))
            col_names = ", ".join(values.keys())
            conn.execute(
                f"INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})",
                list(values.values()),
            )
        return "new"

    diffs = diff_rows(existing, {**existing, **values})
    if not diffs:
        return "skipped"

    _log(logger, f"  ~ UPD [{table}] {row_id}  {row_label(existing)}")
    for line in diffs:
        _log(logger, line)
    if not dry_run:
        set_clause = ", ".join(f"{key} = ?" for key in values)
        conn.execute(
            f"UPDATE {table} SET {set_clause} WHERE id = ?",
            list(values.values()) + [row_id],
        )
    return "updated"


def import_dependencies(
    conn: sqlite3.Connection,
    payload: dict,
    dry_run: bool,
    logger: Logger = print,
) -> int:
    """Insère les contributeurs et sources embarqués, sans écraser l'existant."""
    imported = 0
    for contributor in payload.get("contributors", []):
        existing = fetch_by_id(conn, "contributors", contributor.get("id", ""))
        if existing:
            continue
        cols = table_columns(conn, "contributors")
        values = {column: contributor.get(column) for column in cols if column in contributor}
        if not values.get("id"):
            continue
        if not dry_run:
            placeholders = ", ".join("?" * len(values))
            col_names = ", ".join(values.keys())
            conn.execute(
                f"INSERT OR IGNORE INTO contributors ({col_names}) VALUES ({placeholders})",
                list(values.values()),
            )
        imported += 1
        _log(logger, f"  + DEP [contributors] {values.get('id')}  {values.get('name')}")

    for source in payload.get("sources", []):
        existing = fetch_by_id(conn, "sources", source.get("id", ""))
        if existing:
            continue
        cols = table_columns(conn, "sources")
        values = {column: source.get(column) for column in cols if column in source}
        if not values.get("id"):
            continue
        if not dry_run:
            placeholders = ", ".join("?" * len(values))
            col_names = ", ".join(values.keys())
            conn.execute(
                f"INSERT OR IGNORE INTO sources ({col_names}) VALUES ({placeholders})",
                list(values.values()),
            )
        imported += 1
        _log(logger, f"  + DEP [sources] {values.get('id')}  {values.get('title')}")

    return imported


def entries_by_table(entries: list[dict], logger: Logger = print) -> dict[str, list[dict]]:
    by_table: dict[str, list[dict]] = {table: [] for table in TABLES_ORDER}
    for entry in entries:
        table = entry.get("table")
        if table in by_table:
            by_table[table].append(entry)
        else:
            _log(logger, f"[WARN] Table inconnue ignorée : {table!r}")
    return by_table


def apply_contribution_entries(
    conn: sqlite3.Connection,
    entries: list[dict],
    *,
    validate: bool,
    dry_run: bool,
    logger: Logger = print,
) -> ImportStats:
    stats = ImportStats()
    by_table = entries_by_table(entries, logger=logger)
    for table in TABLES_ORDER:
        for entry in by_table[table]:
            result = upsert_row(
                conn,
                table,
                entry.get("data", {}),
                validate=validate,
                dry_run=dry_run,
                logger=logger,
            )
            stats.add(result)
    return stats


def apply_contribution_payload(
    conn: sqlite3.Connection,
    payload: dict,
    *,
    validate: bool,
    dry_run: bool,
    logger: Logger = print,
) -> ImportStats:
    dependencies = import_dependencies(conn, payload, dry_run=dry_run, logger=logger)
    stats = apply_contribution_entries(
        conn,
        payload.get("entries", []),
        validate=validate,
        dry_run=dry_run,
        logger=logger,
    )
    stats.dependencies = dependencies
    return stats
