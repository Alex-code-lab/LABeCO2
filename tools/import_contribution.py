# SPDX-License-Identifier: GPL-3.0-or-later
"""
Importe un fichier de contribution JSON dans la base SQLite LABeCO2.

Usage :
    python tools/import_contribution.py contribution.json [options]

Options :
    --db PATH        Chemin vers labeco2.sqlite  (défaut : private/labeco2.sqlite)
    --validate       Marquer les entrées importées comme validated (défaut : draft)
    --dry-run        Afficher le diff sans appliquer les changements
    --yes            Ne pas demander de confirmation interactive
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TABLES_ORDER = [
    "contributors",
    "sources",
    "emission_factors",
    "materials",
    "commercial_products",
    "product_components",
    "transport_factors",
]

# Colonnes non affichées dans le diff (techniques, peu lisibles)
_SKIP_DIFF_COLS = {"name_key", "contribution_id", "revision_of_id", "validated_by_id",
                   "validated_at", "deprecated_at", "updated_at"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_by_id(conn: sqlite3.Connection, table: str, row_id: str) -> dict | None:
    conn.row_factory = sqlite3.Row
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    return dict(row) if row else None


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def diff_rows(old: dict, new: dict) -> list[str]:
    lines = []
    all_keys = sorted(set(old) | set(new))
    for k in all_keys:
        if k in _SKIP_DIFF_COLS:
            continue
        v_old = old.get(k)
        v_new = new.get(k)
        if v_old != v_new:
            lines.append(f"  {k}: {v_old!r}  →  {v_new!r}")
    return lines


def upsert_row(
    conn: sqlite3.Connection,
    table: str,
    data: dict,
    validate: bool,
    dry_run: bool,
) -> str:
    """Insère ou met à jour une ligne. Retourne 'new', 'updated', ou 'skipped'."""
    row_id = data.get("id")
    existing = fetch_by_id(conn, table, row_id) if row_id else None
    cols = table_columns(conn, table)

    # Préparer les valeurs à insérer (uniquement colonnes connues)
    values = {c: data.get(c) for c in cols if c in data}
    values["updated_at"] = now_iso()
    if validate and "status" in cols:
        values["status"] = "validated"
        values["validated_at"] = now_iso()

    if existing is None:
        action = "NEW"
        print(f"  + {action} [{table}] {row_id}  {data.get('name') or data.get('title') or data.get('origin') or ''}")
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

    print(f"  ~ UPD [{table}] {row_id}  {existing.get('name') or existing.get('title') or existing.get('origin') or ''}")
    for line in diffs:
        print(line)
    if not dry_run:
        set_clause = ", ".join(f"{k} = ?" for k in values)
        conn.execute(
            f"UPDATE {table} SET {set_clause} WHERE id = ?",
            list(values.values()) + [row_id],
        )
    return "updated"


def import_dependencies(
    conn: sqlite3.Connection,
    payload: dict,
    dry_run: bool,
) -> None:
    """Insère les contributeurs et sources embarqués (sans écraser ce qui existe)."""
    for contributor in payload.get("contributors", []):
        existing = fetch_by_id(conn, "contributors", contributor.get("id", ""))
        if existing:
            continue
        cols = table_columns(conn, "contributors")
        values = {c: contributor.get(c) for c in cols if c in contributor}
        if not dry_run and values.get("id"):
            placeholders = ", ".join("?" * len(values))
            col_names = ", ".join(values.keys())
            conn.execute(
                f"INSERT OR IGNORE INTO contributors ({col_names}) VALUES ({placeholders})",
                list(values.values()),
            )
            print(f"  + DEP [contributors] {values.get('id')}  {values.get('name')}")

    for source in payload.get("sources", []):
        existing = fetch_by_id(conn, "sources", source.get("id", ""))
        if existing:
            continue
        cols = table_columns(conn, "sources")
        values = {c: source.get(c) for c in cols if c in source}
        if not dry_run and values.get("id"):
            placeholders = ", ".join("?" * len(values))
            col_names = ", ".join(values.keys())
            conn.execute(
                f"INSERT OR IGNORE INTO sources ({col_names}) VALUES ({placeholders})",
                list(values.values()),
            )
            print(f"  + DEP [sources] {values.get('id')}  {values.get('title')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import de contribution LABeCO2")
    parser.add_argument("contribution_file")
    parser.add_argument("--db", default=str(ROOT / "private" / "labeco2.sqlite"))
    parser.add_argument("--validate", action="store_true",
                        help="Marquer les entrées importées comme validated")
    parser.add_argument("--dry-run", action="store_true",
                        help="Afficher le diff sans modifier la base")
    parser.add_argument("--yes", action="store_true",
                        help="Ne pas demander de confirmation")
    args = parser.parse_args()

    contrib_path = Path(args.contribution_file)
    if not contrib_path.exists():
        sys.exit(f"Fichier introuvable : {contrib_path}")

    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"Base introuvable : {db_path}")

    with open(contrib_path, encoding="utf-8") as fh:
        payload = json.load(fh)

    fmt = payload.get("format_version")
    if fmt != "1":
        sys.exit(f"Format de contribution non supporté : {fmt!r}")

    entries = payload.get("entries", [])
    exported_at = payload.get("exported_at", "?")
    exporter = (payload.get("contributor") or {}).get("name", "inconnu")

    print(f"Contribution exportée le {exported_at} par {exporter!r}")
    print(f"Entrées : {len(entries)}")
    if args.dry_run:
        print("[DRY-RUN] Aucune modification ne sera appliquée.\n")
    if args.validate:
        print("[VALIDATE] Les entrées seront marquées validated.\n")

    # Grouper par table dans l'ordre d'insertion (pour les FK)
    by_table: dict[str, list[dict]] = {t: [] for t in TABLES_ORDER}
    for entry in entries:
        t = entry.get("table")
        if t in by_table:
            by_table[t].append(entry)
        else:
            print(f"[WARN] Table inconnue ignorée : {t!r}", file=sys.stderr)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    stats = {"new": 0, "updated": 0, "skipped": 0}

    print("\n--- Dépendances ---")
    import_dependencies(conn, payload, dry_run=args.dry_run)

    print("\n--- Entrées ---")
    for table in TABLES_ORDER:
        for entry in by_table[table]:
            result = upsert_row(
                conn, table, entry.get("data", {}),
                validate=args.validate, dry_run=args.dry_run,
            )
            stats[result] += 1

    print(
        f"\nRésumé : {stats['new']} nouvelles, "
        f"{stats['updated']} mises à jour, "
        f"{stats['skipped']} inchangées."
    )

    if args.dry_run:
        conn.close()
        return

    if not args.yes:
        answer = input("\nAppliquer ces modifications ? [o/N] ").strip().lower()
        if answer not in ("o", "oui", "y", "yes"):
            conn.rollback()
            conn.close()
            print("Annulé.")
            return

    conn.commit()
    conn.close()
    print("Import terminé.")


if __name__ == "__main__":
    main()
