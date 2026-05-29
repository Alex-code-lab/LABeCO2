# SPDX-License-Identifier: GPL-3.0-or-later
"""Normalise tous les gants nitrile à 13g de Nitrile (29 mai 2026).

Contexte : la comparaison LABeCO2 vs PER1p5 sur les gants nitrile (Kimtech 90627)
a montré une surestimation de LABeCO2 (108 g CO2e vs 78 g PER1p5). Le facteur
matériau Nitrile (6.4 kg CO2e/kg) est conservé, mais la masse a été harmonisée
à 13 g par paire pour tous les gants nitrile en base — valeur médiane cohérente
avec les datasheets fabricants (Kimtech 90628 = 12.888 g, GANTS NITRILE
Fisherbrand = 13.2 g).

Logique appliquée :
  - Critère : NACRES = HA01 et nom contient « nitrile » / « NBR » / « Kimtech »
    et nom ne contient PAS « latex » / « acetonitrile ».
  - Si le produit a déjà un composant Nitrile : UPDATE mass_g = 13.
  - Sinon : INSERT un composant (component_type='product', mass_g=13, material=Nitrile).
  - Les composants emballage (Carton, etc.) ne sont pas touchés.

Usage :
    python tools/migration/patch_nitrile_gloves_20260529.py             # dry-run
    python tools/migration/patch_nitrile_gloves_20260529.py --apply      # applique
    python tools/migration/patch_nitrile_gloves_20260529.py --db PATH    # autre base
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "private" / "labeco2.sqlite"

TARGET_MASS_G = 13.0


def backup(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = db_path.with_name(f"{db_path.name}.backup_before_patch_{stamp}")
    shutil.copy2(db_path, target)
    return target


def get_nitrile_material_id(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        """
        SELECT m.id
        FROM materials m
        WHERE m.name = 'Nitrile' AND COALESCE(m.status, '') != 'deprecated'
        LIMIT 1
        """
    ).fetchone()
    if not row:
        raise RuntimeError("Matériau 'Nitrile' introuvable en base.")
    return row[0]


def list_targets(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT cp.id, cp.name, cp.reference
        FROM commercial_products cp
        WHERE COALESCE(cp.status, '') != 'deprecated'
          AND cp.code_nacres = 'HA01'
          AND (
              lower(cp.name) LIKE '%nitrile%'
           OR lower(cp.name) LIKE '%nbr%'
           OR lower(cp.name) LIKE '%kimtech%'
          )
          AND lower(cp.name) NOT LIKE '%acetonitrile%'
          AND lower(cp.name) NOT LIKE '%latex%'
        ORDER BY cp.name
        """
    ).fetchall()
    return [dict(r) for r in rows]


def find_nitrile_component(conn: sqlite3.Connection, product_id: str, nitrile_id: str) -> dict | None:
    """Cherche un composant Nitrile (par ID ou nom) sur ce produit."""
    row = conn.execute(
        """
        SELECT pc.id, pc.mass_g
        FROM product_components pc
        LEFT JOIN materials m ON m.id = pc.material_id
        WHERE pc.product_id = ?
          AND (pc.material_id = ? OR m.name = 'Nitrile')
        LIMIT 1
        """,
        (product_id, nitrile_id),
    ).fetchone()
    return dict(row) if row else None


def patch(conn: sqlite3.Connection) -> dict:
    nitrile_id = get_nitrile_material_id(conn)
    targets = list_targets(conn)
    stats = {"updated": 0, "inserted": 0, "noop": 0, "total": len(targets)}
    log = []

    for prod in targets:
        existing = find_nitrile_component(conn, prod["id"], nitrile_id)
        if existing:
            if existing["mass_g"] == TARGET_MASS_G:
                stats["noop"] += 1
                log.append(f"= {prod['name'][:50]:50} ref={prod['reference']:12} déjà à 13g")
            else:
                conn.execute(
                    "UPDATE product_components SET mass_g = ? WHERE id = ?",
                    (TARGET_MASS_G, existing["id"]),
                )
                stats["updated"] += 1
                log.append(
                    f"~ {prod['name'][:50]:50} ref={prod['reference']:12} "
                    f"{existing['mass_g']}g → 13g"
                )
        else:
            new_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO product_components (
                    id, product_id, component_type, material_id, mass_g, units_divisor
                ) VALUES (?, ?, 'product', ?, ?, 1)
                """,
                (new_id, prod["id"], nitrile_id, TARGET_MASS_G),
            )
            stats["inserted"] += 1
            log.append(
                f"+ {prod['name'][:50]:50} ref={prod['reference']:12} → 13g Nitrile (nouveau)"
            )

    return {"stats": stats, "log": log}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--apply", action="store_true", help="Écrit réellement (sinon dry-run + rollback).")
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="N'affiche pas la liste détaillée.")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Base SQLite introuvable : {db_path}", file=sys.stderr)
        return 2

    mode = "APPLIQUÉ" if args.apply else "DRY-RUN"
    print(f"=== Patch nitrile gloves — mode : {mode} ===")
    print(f"Base : {db_path}")

    backup_path: Path | None = None
    if args.apply and not args.no_backup:
        backup_path = backup(db_path)
        print(f"Sauvegarde : {backup_path}")

    conn = sqlite3.connect(db_path)
    try:
        result = patch(conn)
        if not args.quiet:
            for line in result["log"]:
                print(f"  {line}")
        s = result["stats"]
        print(
            f"\nRésumé : {s['total']} gants candidats — "
            f"+{s['inserted']} insertions, ~{s['updated']} mises à jour, ={s['noop']} déjà OK"
        )
        if args.apply:
            conn.commit()
            print("✅ Modifications committées.")
        else:
            conn.rollback()
            print("ℹ️  Dry-run : rien écrit. Relancez avec --apply.")
    except Exception as exc:
        conn.rollback()
        print(f"\n❌ Erreur, rollback : {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
