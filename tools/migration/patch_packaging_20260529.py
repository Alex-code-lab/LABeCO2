# SPDX-License-Identifier: GPL-3.0-or-later
"""Corrige les conditionnements et emballages de 3 produits (29 mai 2026).

Audit suite à comparaison LABeCO2 vs PER1p5 :

  1. Falcon 50 mL bulk (Corning 352070)
     - units_per_sold_packaging : 14 → 500
       (datasheet Corning : 25/Bag, 500/Case)

  2. Kimtech 90627 (gants M)
     - Ajout d'un composant primary_packaging : 15.682 g de Carton
       (copié de la version L 90628, boîte identique)
     - units_per_sold_packaging : NULL → 50
       (Kimtech pack of 100 gloves = 50 paires)

  3. Kimtech 90628 (gants L)
     - units_per_sold_packaging : 25 → 50
       (Kimtech pack of 100 gloves = 50 paires)

Usage :
    python tools/migration/patch_packaging_20260529.py             # dry-run
    python tools/migration/patch_packaging_20260529.py --apply
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "private" / "labeco2.sqlite"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def backup(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = db_path.with_name(f"{db_path.name}.backup_before_patch_{stamp}")
    shutil.copy2(db_path, target)
    return target


def get_carton_material_id(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT id FROM materials WHERE name = 'Carton' AND COALESCE(status, '') != 'deprecated' LIMIT 1"
    ).fetchone()
    if not row:
        raise RuntimeError("Matériau 'Carton' introuvable en base.")
    return row[0]


def find_product(conn: sqlite3.Connection, reference: str) -> dict | None:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT id, name, units_per_sold_packaging
        FROM commercial_products
        WHERE reference = ? AND COALESCE(status, '') != 'deprecated'
        ORDER BY CASE status WHEN 'validated' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END
        LIMIT 1
        """,
        (reference,),
    ).fetchone()
    return dict(row) if row else None


def has_carton_packaging(conn: sqlite3.Connection, product_id: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM product_components pc
        JOIN materials m ON m.id = pc.material_id
        WHERE pc.product_id = ?
          AND pc.component_type = 'primary_packaging'
          AND m.name = 'Carton'
        LIMIT 1
        """,
        (product_id,),
    ).fetchone()
    return row is not None


def patch(conn: sqlite3.Connection) -> list[str]:
    log: list[str] = []
    now = now_iso()
    carton_id = get_carton_material_id(conn)
    log.append(f"Carton material_id : {carton_id[:8]}…")

    # ───── 1. Falcon 50 mL : units 14 → 500 ─────
    p = find_product(conn, "352070")
    if p:
        old = p["units_per_sold_packaging"]
        conn.execute(
            """UPDATE commercial_products
               SET units_per_sold_packaging = 500, updated_at = ?
               WHERE id = ?""",
            (now, p["id"]),
        )
        log.append(f"[1] Falcon 50 mL (id={p['id'][:8]}…) units_per_sold_packaging {old} → 500")
    else:
        log.append("[1] Falcon 50 mL : produit introuvable → skip")

    # ───── 2. Kimtech 90627 (M) : ajouter packaging + units = 50 ─────
    p = find_product(conn, "90627")
    if p:
        old = p["units_per_sold_packaging"]
        if has_carton_packaging(conn, p["id"]):
            log.append(f"[2] Kimtech 90627 (M) : packaging Carton déjà présent, units {old} → 50")
            conn.execute(
                """UPDATE commercial_products
                   SET units_per_sold_packaging = 50, updated_at = ?
                   WHERE id = ?""",
                (now, p["id"]),
            )
        else:
            new_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO product_components (
                       id, product_id, component_type, material_id, mass_g, units_divisor
                   ) VALUES (?, ?, 'primary_packaging', ?, 15.682, 1)""",
                (new_id, p["id"], carton_id),
            )
            conn.execute(
                """UPDATE commercial_products
                   SET units_per_sold_packaging = 50, updated_at = ?
                   WHERE id = ?""",
                (now, p["id"]),
            )
            log.append(
                f"[2] Kimtech 90627 (M) : + composant primary_packaging 15.682g Carton, "
                f"units {old} → 50"
            )
    else:
        log.append("[2] Kimtech 90627 (M) : produit introuvable → skip")

    # ───── 3. Kimtech 90628 (L) : units 25 → 50 ─────
    p = find_product(conn, "90628")
    if p:
        old = p["units_per_sold_packaging"]
        conn.execute(
            """UPDATE commercial_products
               SET units_per_sold_packaging = 50, updated_at = ?
               WHERE id = ?""",
            (now, p["id"]),
        )
        log.append(f"[3] Kimtech 90628 (L) (id={p['id'][:8]}…) units_per_sold_packaging {old} → 50")
    else:
        log.append("[3] Kimtech 90628 (L) : produit introuvable → skip")

    return log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Base SQLite introuvable : {db_path}", file=sys.stderr)
        return 2

    mode = "APPLIQUÉ" if args.apply else "DRY-RUN"
    print(f"=== Patch packaging corrections — mode : {mode} ===")
    print(f"Base : {db_path}")

    backup_path = None
    if args.apply and not args.no_backup:
        backup_path = backup(db_path)
        print(f"Sauvegarde : {backup_path}")

    conn = sqlite3.connect(db_path)
    try:
        log = patch(conn)
        for line in log:
            print(f"  {line}")
        if args.apply:
            conn.commit()
            print("\n✅ Modifications committées.")
        else:
            conn.rollback()
            print("\nℹ️  Dry-run : rien écrit. Relancez avec --apply.")
    except Exception as exc:
        conn.rollback()
        print(f"\n❌ Erreur, rollback : {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
