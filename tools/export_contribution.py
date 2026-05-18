# SPDX-License-Identifier: GPL-3.0-or-later
"""
Export les entrées draft de la base SQLite LABeCO2 en JSON de contribution.

Usage :
    python tools/export_contribution.py [options]

Options :
    --db PATH               Chemin vers labeco2.sqlite  (défaut : private/labeco2.sqlite)
    --contributor NAME|ID   Filtrer par contributeur (nom partiel ou UUID)
    --tables TABLE,...      Tables à exporter, séparées par des virgules
                            Valeurs possibles : emission_factors, materials,
                            commercial_products, transport_factors
                            Défaut : toutes
    --all                   Exporter aussi les entrées validated (pas seulement draft)
    --output FILE           Fichier de sortie  (défaut : contribution_<date>_<contributor>.json)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METIER_TABLES = ["emission_factors", "materials", "commercial_products", "transport_factors"]


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def fetch_all(conn: sqlite3.Connection, sql: str, params=()) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [row_to_dict(r) for r in conn.execute(sql, params)]


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
    for e in entries:
        data = e["data"]
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Export des contributions LABeCO2 en JSON")
    parser.add_argument("--db", default=str(ROOT / "private" / "labeco2.sqlite"))
    parser.add_argument("--contributor", default=None)
    parser.add_argument("--tables", default=None)
    parser.add_argument("--all", dest="all_statuses", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"Base introuvable : {db_path}")

    tables_to_export = (
        [t.strip() for t in args.tables.split(",")]
        if args.tables
        else METIER_TABLES
    )
    unknown = [t for t in tables_to_export if t not in METIER_TABLES]
    if unknown:
        sys.exit(f"Tables inconnues : {unknown}. Valeurs possibles : {METIER_TABLES}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    contributor = resolve_contributor(conn, args.contributor)
    extra_filter, filter_params = build_contributor_filter(contributor)
    status_filter = "IN ('draft', 'validated')" if args.all_statuses else "= 'draft'"

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
    conn.close()

    now = datetime.now(timezone.utc).isoformat()
    contributor_name = (contributor or {}).get("name", "inconnu")
    date_slug = datetime.now().strftime("%Y-%m-%d")
    safe_name = contributor_name.replace(" ", "_").replace("/", "_")

    payload = {
        "format_version": "1",
        "exported_at": now,
        "contributor": contributor,
        "sources": sources,
        "contributors": contributors,
        "entries": all_entries,
    }

    output_path = args.output or f"contribution_LABeCO2_{date_slug}_{safe_name}.json"
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)

    n_by_table: dict[str, int] = {}
    for e in all_entries:
        n_by_table[e["table"]] = n_by_table.get(e["table"], 0) + 1

    print(f"Exporté : {output_path}")
    for t, n in sorted(n_by_table.items()):
        print(f"  {t}: {n} entrée(s)")
    print(f"  sources embarquées: {len(sources)}")
    print(f"  contributeurs embarqués: {len(contributors)}")


if __name__ == "__main__":
    main()
