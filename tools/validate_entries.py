# SPDX-License-Identifier: GPL-3.0-or-later
"""
Outil de validation des entrées draft pour le mainteneur LABeCO2.

Usage :
    python tools/validate_entries.py [options]

Options :
    --db PATH             Chemin vers labeco2.sqlite  (défaut : private/labeco2.sqlite)
    --validator NAME|ID   Nom ou UUID du contributeur qui valide (obligatoire sauf --dry-run)
    --table TABLE,...     Filtrer par table(s)
    --contributor NAME    Ne montrer que les drafts d'un contributeur donné
    --all                 Valider toutes les entrées sans confirmation interactive
    --reject-orphans      Déprécier les produits liquides sans facteur d'émission
    --dry-run             Afficher sans modifier
    --yes                 Pas de confirmation finale

Mode interactif (défaut sans --all) :
    Pour chaque entrée : [v]alider  [r]ejeter  [s]auter  [q]uitter
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui.quality_check import check_database, errors as quality_errors

TABLES = ["emission_factors", "materials", "commercial_products", "transport_factors"]

NAME_COL = {
    "emission_factors": "name",
    "materials": "name",
    "commercial_products": "name",
    "transport_factors": "origin",
}

DETAIL_QUERIES = {
    "emission_factors": """
        SELECT ef.name, ef.factor_type, ef.co2_factor,
               ef.uncertainty * 100 AS incert_pct,
               s.title AS source, c.name AS contributor
        FROM emission_factors ef
        LEFT JOIN sources s ON s.id = ef.source_id
        LEFT JOIN contributors c ON c.id = ef.contributor_id
        WHERE ef.id = ?
    """,
    "materials": """
        SELECT m.name, ef.co2_factor, ef.uncertainty,
               s.title AS source, c.name AS contributor
        FROM materials m
        LEFT JOIN emission_factors ef ON ef.id = m.emission_factor_id
        LEFT JOIN sources s ON s.id = m.source_id
        LEFT JOIN contributors c ON c.id = m.contributor_id
        WHERE m.id = ?
    """,
    "commercial_products": """
        SELECT cp.name, cp.code_nacres, cp.product_type,
               cp.units_per_sold_packaging, cp.price_sold_packaging,
               ef.name AS factor_name,
               s.title AS source, c.name AS contributor
        FROM commercial_products cp
        LEFT JOIN emission_factors ef ON ef.id = cp.emission_factor_id
        LEFT JOIN sources s ON s.id = cp.source_id
        LEFT JOIN contributors c ON c.id = cp.contributor_id
        WHERE cp.id = ?
    """,
    "transport_factors": """
        SELECT tf.origin, tf.mode, tf.distance_km,
               tf.factor_kgco2e_per_kg, tf.uncertainty,
               s.title AS source, c.name AS contributor
        FROM transport_factors tf
        LEFT JOIN sources s ON s.id = tf.source_id
        LEFT JOIN contributors c ON c.id = tf.contributor_id
        WHERE tf.id = ?
    """,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_contributor(conn: sqlite3.Connection, selector: str) -> dict | None:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, name FROM contributors WHERE id = ? OR name LIKE ?",
        (selector, f"%{selector}%"),
    ).fetchall()
    if not rows:
        print(f"Contributeur introuvable : {selector!r}", file=sys.stderr)
        return None
    if len(rows) > 1:
        print(f"Plusieurs contributeurs correspondent à {selector!r} :", file=sys.stderr)
        for r in rows:
            print(f"  {r['id']}  {r['name']}", file=sys.stderr)
        return None
    return dict(rows[0])


def fetch_drafts(
    conn: sqlite3.Connection,
    table: str,
    contributor_filter: str | None,
) -> list[dict]:
    conn.row_factory = sqlite3.Row
    col = NAME_COL[table]
    extra = ""
    params: list = []
    if contributor_filter:
        extra = " AND contributor_id = (SELECT id FROM contributors WHERE name LIKE ? LIMIT 1)"
        params.append(f"%{contributor_filter}%")
    rows = conn.execute(
        f"SELECT id, {col} AS name FROM {table} WHERE status = 'draft'{extra} ORDER BY {col}",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def print_detail(conn: sqlite3.Connection, table: str, entry_id: str) -> None:
    conn.row_factory = sqlite3.Row
    row = conn.execute(DETAIL_QUERIES[table], (entry_id,)).fetchone()
    if not row:
        return
    for k, v in dict(row).items():
        if v is not None and str(v).strip():
            print(f"    {k}: {v}")


def validate_entry(
    conn: sqlite3.Connection,
    table: str,
    entry_id: str,
    validator_id: str,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    conn.execute(
        f"""UPDATE {table}
            SET status = 'validated', validated_by_id = ?, validated_at = ?, updated_at = ?
            WHERE id = ?""",
        (validator_id, now_iso(), now_iso(), entry_id),
    )


def reject_entry(
    conn: sqlite3.Connection,
    table: str,
    entry_id: str,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    conn.execute(
        f"""UPDATE {table}
            SET status = 'deprecated', deprecated_at = ?, updated_at = ?
            WHERE id = ?""",
        (now_iso(), now_iso(), entry_id),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validation des drafts LABeCO2")
    parser.add_argument("--db", default=str(ROOT / "private" / "labeco2.sqlite"))
    parser.add_argument("--validator", default=None,
                        help="Nom ou UUID du contributeur validateur (obligatoire)")
    parser.add_argument("--table", default=None,
                        help="Table(s) à valider, séparées par des virgules")
    parser.add_argument("--contributor", default=None,
                        help="Ne montrer que les drafts de ce contributeur")
    parser.add_argument("--all", dest="validate_all", action="store_true",
                        help="Valider toutes les entrées sans mode interactif")
    parser.add_argument("--reject-orphans", action="store_true",
                        help="Déprécier les produits liquides sans facteur d'émission")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"Base introuvable : {db_path}")

    tables = [t.strip() for t in args.table.split(",")] if args.table else TABLES

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    validator = None
    if not args.dry_run:
        if not args.validator:
            sys.exit("--validator requis (ex: --validator Souchaud). Utilisez --dry-run pour afficher sans modifier.")
        validator = resolve_contributor(conn, args.validator)
        if not validator:
            conn.close()
            sys.exit(1)
        print(f"Validateur : {validator['name']}  ({validator['id']})")

    if args.dry_run:
        print("[DRY-RUN] Aucune modification.\n")

    stats = {"validated": 0, "rejected": 0, "skipped": 0}

    for table in tables:
        drafts = fetch_drafts(conn, table, args.contributor)
        if not drafts:
            continue

        print(f"\n{'='*60}")
        print(f"  {table}  —  {len(drafts)} entrée(s) draft")
        print(f"{'='*60}")

        for entry in drafts:
            entry_id = entry["id"]
            entry_name = entry["name"] or entry_id
            print(f"\n  [{table}] {entry_name}")
            print_detail(conn, table, entry_id)

            if args.validate_all:
                action = "v"
            else:
                try:
                    raw = input("  → [v]alider  [r]ejeter  [s]auter  [q]uitter : ").strip().lower()
                except EOFError:
                    raw = "q"
                action = raw[:1] if raw else "s"

            if action == "v":
                validate_entry(conn, table, entry_id, validator["id"] if validator else "", args.dry_run)
                stats["validated"] += 1
                print("    ✓ validé")
            elif action == "r":
                reject_entry(conn, table, entry_id, args.dry_run)
                stats["rejected"] += 1
                print("    ✗ rejeté (deprecated)")
            elif action == "q":
                print("  Arrêt.")
                break
            else:
                stats["skipped"] += 1

    # Traiter les orphelins si demandé
    if args.reject_orphans:
        orphans = conn.execute("""
            SELECT id, name FROM commercial_products
            WHERE product_type = 'liquid'
              AND (emission_factor_id IS NULL OR emission_factor_id = '')
              AND status != 'deprecated'
        """).fetchall()
        if orphans:
            print(f"\n[ORPHELINS] {len(orphans)} produit(s) liquide(s) sans facteur :")
            for row in orphans:
                print(f"  {row[1]}")
                if not args.dry_run:
                    conn.execute(
                        "UPDATE commercial_products SET status='deprecated', deprecated_at=? WHERE id=?",
                        (now_iso(), row[0]),
                    )
                stats["rejected"] += 1

    print(
        f"\nRésumé : {stats['validated']} validées, "
        f"{stats['rejected']} rejetées, "
        f"{stats['skipped']} sautées."
    )

    if args.dry_run:
        conn.close()
        return

    if not args.yes and not args.validate_all:
        answer = input("\nAppliquer ? [o/N] ").strip().lower()
        if answer not in ("o", "oui", "y", "yes"):
            conn.rollback()
            conn.close()
            print("Annulé.")
            return

    conn.commit()
    conn.close()
    print("Terminé.")


if __name__ == "__main__":
    main()
