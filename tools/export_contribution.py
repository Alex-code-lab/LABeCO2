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
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.contribution_io import (
    METIER_TABLES,
    build_contribution_payload,
    build_contributor_filter,
    collect_dependencies,
    collect_product_components,
    default_contribution_path,
    export_table,
    fetch_all,
    resolve_contributor,
    row_to_dict,
    write_contribution_payload,
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

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        payload, contributor = build_contribution_payload(
            conn,
            contributor_selector=args.contributor,
            tables=[t.strip() for t in args.tables.split(",")] if args.tables else None,
            include_validated=args.all_statuses,
        )
    except ValueError as exc:
        sys.exit(str(exc))
    finally:
        conn.close()

    output_path = args.output or default_contribution_path(contributor)
    write_contribution_payload(payload, output_path)

    n_by_table: dict[str, int] = {}
    for e in payload["entries"]:
        n_by_table[e["table"]] = n_by_table.get(e["table"], 0) + 1

    print(f"Exporté : {output_path}")
    for t, n in sorted(n_by_table.items()):
        print(f"  {t}: {n} entrée(s)")
    print(f"  sources embarquées: {len(payload['sources'])}")
    print(f"  contributeurs embarqués: {len(payload['contributors'])}")


if __name__ == "__main__":
    main()
