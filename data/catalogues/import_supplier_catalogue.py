"""
import_supplier_catalogue.py

Importe un CSV de catalogue fournisseur (généré par parse_catalogue.py)
dans la table supplier_catalogue, et crée les entrées manquantes dans
commercial_products (status='pending', à valider manuellement).

Prérequis :
    Migration v2 appliquée (migrate_v2_supplier_catalogue.py)

Usage :
    python data/catalogues/import_supplier_catalogue.py --csv data/catalogues/DUCHEFA/prix_duchefa.csv
    python data/catalogues/import_supplier_catalogue.py --csv data/catalogues/DUCHEFA/prix_duchefa.csv --dry-run
"""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[2]  # LABeCO2/
DB_PATH = ROOT / "data" / "labeco2_reference.sqlite"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _stable_uuid(namespace: str, *parts: str) -> str:
    key = "|".join(str(p) for p in parts)
    return str(uuid.uuid5(uuid.UUID(int=0), f"{namespace}:{key}"))


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


_UNIT_RE = re.compile(
    r'([\d,\.]+)\s*(kg|mg|g\b|litre?s?|l\b|ml|µl|µg|iu|u\b)',
    re.IGNORECASE,
)


def infer_mass_volume(conditionnement: str) -> tuple[float | None, float | None]:
    if not conditionnement:
        return None, None
    m = _UNIT_RE.search(conditionnement.strip())
    if not m:
        return None, None
    qty  = float(m.group(1).replace(',', '.'))
    unit = m.group(2).lower()
    if unit == 'kg':              return qty * 1000, None
    if unit == 'g':               return qty,        None
    if unit == 'mg':              return qty / 1000, None
    if unit == 'µg':              return qty / 1_000_000, None
    if unit in ('l', 'litre', 'litres'): return None, qty * 1000
    if unit == 'ml':              return None, qty
    if unit == 'µl':              return None, qty / 1000
    return None, None


def infer_product_type(conditionnement: str) -> str:
    """'liquid' si unité volumique, 'solid' sinon."""
    if not conditionnement:
        return "solid"
    u = conditionnement.lower()
    if any(k in u for k in ('ml', 'µl', 'litre', 'liter', ' l ')):
        return "liquid"
    return "solid"


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ── Matching avec commercial_products existants ───────────────────────────────

def find_existing_product(
    conn: sqlite3.Connection,
    code_fournisseur: str,
) -> str | None:
    """
    Cherche un commercial_product existant par référence exacte complète.
    Ex : "A0602.0100" → cherche reference = "A0602.0100"
    Pas de fuzzy : chaque conditionnement est un produit distinct.
    """
    cur = conn.execute(
        "SELECT id FROM commercial_products WHERE reference = ? LIMIT 1",
        (code_fournisseur,),
    )
    row = cur.fetchone()
    return row[0] if row else None


# ── Import ─────────────────────────────────────────────────────────────────────

def run(csv_path: Path, dry_run: bool = False) -> None:
    if not DB_PATH.exists():
        print(f"ERREUR : base introuvable à {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Vérifier que la migration v2 est appliquée
    if "supplier_catalogue" not in {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }:
        print("ERREUR : table supplier_catalogue absente.")
        print("Lancez d'abord : python tools/migration/migrate_v2_supplier_catalogue.py")
        conn.close()
        return

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"CSV : {csv_path.name}  ({len(rows)} lignes)")

    now = datetime.now(timezone.utc).isoformat()
    stats = {"inserted_catalogue": 0, "linked": 0, "created_pending": 0, "skipped": 0}

    try:
        conn.execute("BEGIN")

        for row in rows:
            supplier       = row.get("fournisseur", "").strip()
            cat_date       = row.get("catalogue_date", "").strip()
            code_f         = row.get("code_fournisseur", "").strip()
            designation    = row.get("designation", "").strip()
            brand          = row.get("marque", "").strip()
            condt          = row.get("condt", "").strip()
            code_nacres    = row.get("code_nacres", "").strip()

            try:
                price_ht = float(row["prix_ht"]) if row.get("prix_ht") else None
            except ValueError:
                price_ht = None

            try:
                units = int(row["nb_unites"]) if row.get("nb_unites") else 1
            except ValueError:
                units = 1

            if not code_f or price_ht is None:
                stats["skipped"] += 1
                continue

            mass_g, volume_ml = infer_mass_volume(condt)
            product_type      = infer_product_type(condt)

            # ── 1. Insérer dans supplier_catalogue ────────────────────────
            sc_id = _stable_uuid("supplier_catalogue", supplier, code_f)
            conn.execute(
                """
                INSERT OR IGNORE INTO supplier_catalogue
                    (id, supplier, catalogue_date, code_fournisseur, designation,
                     brand, conditionnement, price_ht, units_per_pack,
                     mass_g, volume_ml, imported_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (sc_id, supplier, cat_date, code_f, designation,
                 brand, condt, price_ht, units,
                 mass_g, volume_ml, now),
            )
            if conn.execute(
                "SELECT changes()"
            ).fetchone()[0]:
                stats["inserted_catalogue"] += 1

            # ── 2. Chercher un commercial_product existant ─────────────────
            existing_id = find_existing_product(conn, code_f)

            if existing_id:
                # Lier au catalogue sans écraser les autres champs
                conn.execute(
                    """
                    UPDATE commercial_products
                    SET supplier_catalogue_id = ?
                    WHERE id = ? AND supplier_catalogue_id IS NULL
                    """,
                    (sc_id, existing_id),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    stats["linked"] += 1

            else:
                # ── 3. Créer un nouveau produit en attente de validation ───
                cp_id = _stable_uuid("commercial_products", supplier, code_f)
                # Vérifier qu'il n'existe pas déjà (idempotence)
                exists = conn.execute(
                    "SELECT 1 FROM commercial_products WHERE id = ?", (cp_id,)
                ).fetchone()
                if not exists:
                    conn.execute(
                        """
                        INSERT INTO commercial_products
                            (id, name, brand, reference, code_nacres,
                             product_type, sold_packaging_label,
                             units_per_sold_packaging, price_sold_packaging,
                             sold_unit_volume_ml,
                             supplier_catalogue_id,
                             status, created_at, updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            cp_id,
                            designation or f"{supplier} {code_f}",
                            brand,
                            code_f,   # référence complète avec pack code ex. "A0501.1000"
                            code_nacres or None,
                            product_type,
                            condt,
                            units,
                            price_ht,
                            volume_ml,              # None si solide
                            sc_id,
                            "pending",
                            now, now,
                        ),
                    )
                    stats["created_pending"] += 1

        if dry_run:
            conn.execute("ROLLBACK")
            print("\nDRY-RUN — aucune modification.")
        else:
            conn.execute("COMMIT")

    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"ERREUR : {e}")
        raise
    finally:
        conn.close()

    # ── Résumé ─────────────────────────────────────────────────────────────
    print(f"\n{'─'*55}")
    print(f"Lignes ignorées (sans ref/prix)    : {stats['skipped']}")
    print(f"Insérées dans supplier_catalogue   : {stats['inserted_catalogue']}")
    print(f"Liées à un produit existant        : {stats['linked']}")
    print(f"Nouveaux produits (status=pending) : {stats['created_pending']}")
    print(f"{'─'*55}")
    if stats["created_pending"] and not dry_run:
        print(
            f"\n→ {stats['created_pending']} produits à valider dans l'interface "
            "(code NACRES manquant)."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv", required=True,
        help="CSV généré par parse_catalogue.py",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simuler sans modifier la base",
    )
    args = parser.parse_args()
    run(Path(args.csv), dry_run=args.dry_run)
