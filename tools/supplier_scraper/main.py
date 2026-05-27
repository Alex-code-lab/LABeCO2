# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI du scraper prudent de références fournisseurs.

Exemples :
    python -m tools.supplier_scraper.main --config tools/supplier_scraper/config.yaml --dry-run
    python -m tools.supplier_scraper.main --config tools/supplier_scraper/config.yaml --supplier VWR
    python -m tools.supplier_scraper.main --config tools/supplier_scraper/config.yaml --export-csv exports/supplier_refs.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")

if __package__ in {None, ""} and str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.supplier_scraper.config import enabled_suppliers, load_config
from tools.supplier_scraper.crawler import SupplierCrawler
from tools.supplier_scraper.storage import SupplierStorage


def _setup_logging(config: dict) -> None:
    log_cfg = config.get("logging", {})
    level = getattr(logging, str(log_cfg.get("level", "INFO")).upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s:%(name)s:%(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scraper prudent de références fournisseurs LABeCO2")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Chemin du config.yaml")
    parser.add_argument("--supplier", default="", help="Limiter à un fournisseur activé par nom")
    parser.add_argument("--db", default="", help="Surcharge le chemin SQLite de la configuration")
    parser.add_argument("--dry-run", action="store_true", help="Analyse sans écrire en base")
    parser.add_argument("--export-csv", default="", help="Exporter les références fournisseur en CSV")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)
    _setup_logging(config)

    db_path = Path(args.db or config.get("database_path") or ROOT / "private" / "labeco2.sqlite")
    storage = SupplierStorage(db_path)

    if args.export_csv:
        with storage.connect() as conn:
            count = storage.export_references_csv(conn, args.export_csv, supplier=args.supplier)
        print(f"Export CSV : {args.export_csv} ({count} ligne(s))")
        return 0

    dry_run = bool(args.dry_run or config.get("dry_run", True))
    suppliers = enabled_suppliers(config)
    if args.supplier:
        suppliers = [supplier for supplier in suppliers if supplier.get("name") == args.supplier]
    if not suppliers:
        print("Aucun fournisseur activé. Activez d'abord un fournisseur dans config.yaml.")
        return 1

    exit_code = 0
    for supplier in suppliers:
        crawler = SupplierCrawler(config, supplier, storage)
        stats = crawler.run(dry_run=dry_run, config_path=str(config_path))
        print(
            f"{supplier['name']}: pages={stats.fetched_pages}, "
            f"produits={stats.product_pages}, références={stats.stored_references}, "
            f"nouvelles={stats.new_references}, déjà_connues={stats.known_references}, "
            f"sans_ref={stats.skipped_without_ref}, arrêt={stats.stopped_reason or '-'}"
        )
        if stats.stopped_reason:
            exit_code = 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
