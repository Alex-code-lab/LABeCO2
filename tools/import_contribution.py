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
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.contribution_io import (
    TABLES_ORDER,
    apply_contribution_entries,
    diff_rows,
    fetch_by_id,
    import_dependencies,
    load_contribution_payload,
    now_iso,
    table_columns,
    upsert_row,
)
from ui.quality_check import check_database, errors as quality_errors, format_issues


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

    try:
        payload = load_contribution_payload(contrib_path)
    except ValueError as exc:
        sys.exit(str(exc))

    entries = payload.get("entries", [])
    exported_at = payload.get("exported_at", "?")
    exporter = (payload.get("contributor") or {}).get("name", "inconnu")

    print(f"Contribution exportée le {exported_at} par {exporter!r}")
    print(f"Entrées : {len(entries)}")
    if args.dry_run:
        print("[DRY-RUN] Aucune modification ne sera appliquée.\n")
    if args.validate:
        print("[VALIDATE] Les entrées seront marquées validated.\n")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    print("\n--- Dépendances ---")
    dep_count = import_dependencies(conn, payload, dry_run=args.dry_run, logger=print)
    print("\n--- Entrées ---")
    stats = apply_contribution_entries(
        conn,
        payload.get("entries", []),
        validate=args.validate,
        dry_run=args.dry_run,
        logger=print,
    )
    stats.dependencies = dep_count

    print(
        f"\nRésumé : {stats.new} nouvelles, "
        f"{stats.updated} mises à jour, "
        f"{stats.skipped} inchangées."
    )

    if args.dry_run:
        conn.close()
        return

    # Rapport qualité sur les nouvelles entrées avant commit
    db_issues = quality_errors(check_database(conn))
    if db_issues:
        print(f"\n[QUALITÉ] {len(db_issues)} erreur(s) bloquante(s) détectée(s) après import :")
        print(format_issues(db_issues))
        if not args.yes:
            answer = input("\nCes erreurs sont présentes. Annuler l'import ? [O/n] ").strip().lower()
            if answer not in ("n", "non", "no"):
                conn.rollback()
                conn.close()
                print("Annulé.")
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
