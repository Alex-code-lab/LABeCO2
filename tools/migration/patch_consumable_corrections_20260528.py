# SPDX-License-Identifier: GPL-3.0-or-later
"""Corrections de qualité sur 7 consommables (28 mai 2026).

Origine : audit du fichier `data/mass_factors/masses_consommable_bis.csv`.
Vérifications faites en ligne sur les datasheets fournisseurs des produits.

Corrections appliquées (commercial_products + product_components) :
  1. Falcon Petri 351008  : matériau PP → PS
  2. Starlab E4860-0005   : matériau Verre → PS
  3. Kimtech 90628 gants L: matériau PP → Nitrile, NACRES NB13 → HA01
  4. Falcon 50 mL 352070  : masse 8.15g → 14.35g, NACRES NB13 → NB11
  5. TPP Dish 60 (93060)  : matériau PP → PS (corps), NACRES NB03 → NB13
  6. Corning 430829 50 mL : matériau PET → PP, masse 12.2g → 14.0g, NACRES NB13 → NB11

Le FlipTube Hamilton 235454 a déjà été déprécié dans une opération précédente,
il n'est donc pas touché ici.

Usage :
    # Aperçu sans écriture (rollback)
    python tools/migration/patch_consumable_corrections_20260528.py

    # Application réelle (avec backup auto)
    python tools/migration/patch_consumable_corrections_20260528.py --apply

    # Cible une autre base
    python tools/migration/patch_consumable_corrections_20260528.py --db PATH --apply
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
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


# ----------------------------------------------------------------------------
# Helpers de résolution d'IDs
# ----------------------------------------------------------------------------


def get_material_id(conn: sqlite3.Connection, name: str) -> str:
    """Retourne l'ID du matériau actif le plus utilisé pour ce nom."""
    row = conn.execute(
        """
        SELECT m.id, COUNT(pc.product_id) AS n
        FROM materials m
        LEFT JOIN product_components pc ON pc.material_id = m.id
        WHERE m.name = ? AND COALESCE(m.status, '') != 'deprecated'
        GROUP BY m.id
        ORDER BY n DESC
        LIMIT 1
        """,
        (name,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"Matériau introuvable : {name!r}")
    return row[0]


def find_product(conn: sqlite3.Connection, reference: str, status_in: tuple[str, ...] | None = None) -> dict | None:
    """Retourne le 1er produit non déprécié pour cette référence (status_in filtre fin)."""
    query = """
        SELECT id, name, code_nacres, status
        FROM commercial_products
        WHERE reference = ?
          AND COALESCE(status, '') != 'deprecated'
    """
    params: list = [reference]
    if status_in:
        placeholders = ",".join("?" * len(status_in))
        query += f" AND COALESCE(status, '') IN ({placeholders})"
        params.extend(status_in)
    query += " ORDER BY CASE status WHEN 'validated' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END LIMIT 1"
    row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def find_component(
    conn: sqlite3.Connection,
    product_id: str,
    expected_material_id: str | None = None,
) -> dict | None:
    """Premier composant non-emballage du produit (exclut Carton, PE wrapper).

    Si `expected_material_id` est fourni, on cherche d'abord le composant ayant
    ce material_id, puis comme fallback un composant ayant le même *nom* de
    matériau (utile quand la base contient plusieurs IDs pour le même matériau).
    """
    conn.row_factory = sqlite3.Row
    if expected_material_id:
        row = conn.execute(
            """
            SELECT pc.id, pc.mass_g, m.name AS material
            FROM product_components pc
            LEFT JOIN materials m ON m.id = pc.material_id
            WHERE pc.product_id = ? AND pc.material_id = ?
            LIMIT 1
            """,
            (product_id, expected_material_id),
        ).fetchone()
        if not row:
            # Fallback : match par NOM de matériau (cas doublon d'IDs)
            expected_name = conn.execute(
                "SELECT name FROM materials WHERE id = ?",
                (expected_material_id,),
            ).fetchone()
            if expected_name:
                row = conn.execute(
                    """
                    SELECT pc.id, pc.mass_g, m.name AS material
                    FROM product_components pc
                    JOIN materials m ON m.id = pc.material_id
                    WHERE pc.product_id = ? AND m.name = ?
                    LIMIT 1
                    """,
                    (product_id, expected_name[0]),
                ).fetchone()
    else:
        # Sinon, le composant le plus lourd hors Carton/PE
        row = conn.execute(
            """
            SELECT pc.id, pc.mass_g, m.name AS material
            FROM product_components pc
            LEFT JOIN materials m ON m.id = pc.material_id
            WHERE pc.product_id = ?
              AND COALESCE(m.name, '') NOT IN ('Carton', 'Polyéthylène (PE)', 'Papier')
            ORDER BY pc.mass_g DESC NULLS LAST
            LIMIT 1
            """,
            (product_id,),
        ).fetchone()
    return dict(row) if row else None


# ----------------------------------------------------------------------------
# Application
# ----------------------------------------------------------------------------


def patch(conn: sqlite3.Connection, *, dry_run: bool) -> list[str]:
    """Applique les 6 corrections. Retourne la liste des actions effectuées."""
    log: list[str] = []
    now = now_iso()

    # Résolution des IDs matériaux
    mat_pp = get_material_id(conn, "Polypropylène (PP)")
    mat_ps = get_material_id(conn, "Polystyrène (PS)")
    mat_pet = get_material_id(conn, "Polyéthylène téréphtalate (PET)")
    mat_nitrile = get_material_id(conn, "Nitrile")
    mat_verre = get_material_id(conn, "Verre")
    log.append(f"Matériaux résolus : PP={mat_pp[:8]}… PS={mat_ps[:8]}… PET={mat_pet[:8]}… Nitrile={mat_nitrile[:8]}… Verre={mat_verre[:8]}…")

    # ───────────────────────────────────────────────────────────────────────
    # 1. Falcon Petri 351008 : PP → PS
    # ───────────────────────────────────────────────────────────────────────
    p = find_product(conn, "351008")
    if p:
        comp = find_component(conn, p["id"], expected_material_id=mat_pp)
        if comp:
            log.append(f"[1] Falcon 351008 (id={p['id'][:8]}…) : composant {comp['id'][:8]}… PP→PS")
            conn.execute(
                "UPDATE product_components SET material_id = ? WHERE id = ?",
                (mat_ps, comp["id"]),
            )
            conn.execute(
                "UPDATE commercial_products SET updated_at = ? WHERE id = ?",
                (now, p["id"]),
            )
        else:
            log.append("[1] Falcon 351008 : composant PP introuvable → skip")
    else:
        log.append("[1] Falcon 351008 : produit introuvable → skip")

    # ───────────────────────────────────────────────────────────────────────
    # 2. Starlab E4860-0005 : Verre → PS
    # ───────────────────────────────────────────────────────────────────────
    p = find_product(conn, "E4860-0005")
    if p:
        comp = find_component(conn, p["id"], expected_material_id=mat_verre)
        if comp:
            log.append(f"[2] Starlab E4860 (id={p['id'][:8]}…) : composant {comp['id'][:8]}… Verre→PS")
            conn.execute(
                "UPDATE product_components SET material_id = ? WHERE id = ?",
                (mat_ps, comp["id"]),
            )
            conn.execute(
                "UPDATE commercial_products SET updated_at = ? WHERE id = ?",
                (now, p["id"]),
            )
        else:
            log.append("[2] Starlab E4860 : composant Verre introuvable → skip")
    else:
        log.append("[2] Starlab E4860 : produit introuvable → skip")

    # ───────────────────────────────────────────────────────────────────────
    # 3. Kimtech 90628 (gants L) : PP→Nitrile + NACRES NB13→HA01
    # ───────────────────────────────────────────────────────────────────────
    p = find_product(conn, "90628")
    if p:
        comp = find_component(conn, p["id"], expected_material_id=mat_pp)
        if comp:
            log.append(
                f"[3] Kimtech 90628 (id={p['id'][:8]}…) : NACRES {p['code_nacres']}→HA01, "
                f"composant {comp['id'][:8]}… PP→Nitrile"
            )
            conn.execute(
                "UPDATE product_components SET material_id = ? WHERE id = ?",
                (mat_nitrile, comp["id"]),
            )
            conn.execute(
                "UPDATE commercial_products SET code_nacres = 'HA01', updated_at = ? WHERE id = ?",
                (now, p["id"]),
            )
        else:
            log.append("[3] Kimtech 90628 : composant PP introuvable → skip")
    else:
        log.append("[3] Kimtech 90628 : produit introuvable → skip")

    # ───────────────────────────────────────────────────────────────────────
    # 4. Falcon 50 mL bulk (352070) : masse 8.15→14.35, NACRES NB13→NB11
    #    Cible le produit non déprécié (le draft).
    # ───────────────────────────────────────────────────────────────────────
    p = find_product(conn, "352070")
    if p:
        comp = find_component(conn, p["id"], expected_material_id=mat_pp)
        if comp:
            log.append(
                f"[4] Falcon 352070 (id={p['id'][:8]}…) : NACRES {p['code_nacres']}→NB11, "
                f"composant {comp['id'][:8]}… masse {comp['mass_g']}→14.35g"
            )
            conn.execute(
                "UPDATE product_components SET mass_g = 14.35 WHERE id = ?",
                (comp["id"],),
            )
            conn.execute(
                "UPDATE commercial_products SET code_nacres = 'NB11', updated_at = ? WHERE id = ?",
                (now, p["id"]),
            )
        else:
            log.append("[4] Falcon 352070 : composant PP introuvable → skip")
    else:
        log.append("[4] Falcon 352070 : produit actif introuvable → skip")

    # ───────────────────────────────────────────────────────────────────────
    # 5. TPP Dish 60 (93060) : corps PP→PS, NACRES NB03→NB13
    # ───────────────────────────────────────────────────────────────────────
    p = find_product(conn, "93060")
    if p:
        comp = find_component(conn, p["id"], expected_material_id=mat_pp)
        if comp:
            log.append(
                f"[5] TPP 93060 (id={p['id'][:8]}…) : NACRES {p['code_nacres']}→NB13, "
                f"composant {comp['id'][:8]}… PP→PS (corps)"
            )
            conn.execute(
                "UPDATE product_components SET material_id = ? WHERE id = ?",
                (mat_ps, comp["id"]),
            )
            conn.execute(
                "UPDATE commercial_products SET code_nacres = 'NB13', updated_at = ? WHERE id = ?",
                (now, p["id"]),
            )
        else:
            log.append("[5] TPP 93060 : composant PP introuvable → skip")
    else:
        log.append("[5] TPP 93060 : produit introuvable → skip")

    # ───────────────────────────────────────────────────────────────────────
    # 6. Corning 430829 50 mL : PET→PP, masse 12.2→14.0, NACRES NB13→NB11
    # ───────────────────────────────────────────────────────────────────────
    p = find_product(conn, "430829")
    if p:
        comp = find_component(conn, p["id"], expected_material_id=mat_pet)
        if comp:
            log.append(
                f"[6] Corning 430829 (id={p['id'][:8]}…) : NACRES {p['code_nacres']}→NB11, "
                f"composant {comp['id'][:8]}… PET→PP, masse {comp['mass_g']}→14.0g"
            )
            conn.execute(
                """UPDATE product_components
                   SET material_id = ?, mass_g = 14.0
                   WHERE id = ?""",
                (mat_pp, comp["id"]),
            )
            conn.execute(
                "UPDATE commercial_products SET code_nacres = 'NB11', updated_at = ? WHERE id = ?",
                (now, p["id"]),
            )
        else:
            log.append("[6] Corning 430829 : composant PET introuvable → skip")
    else:
        log.append("[6] Corning 430829 : produit introuvable → skip")

    return log


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Base SQLite cible.")
    parser.add_argument("--apply", action="store_true", help="Écrit réellement (sinon dry-run + rollback).")
    parser.add_argument("--no-backup", action="store_true", help="Ne crée pas de sauvegarde avant --apply.")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Base SQLite introuvable : {db_path}", file=sys.stderr)
        return 2

    mode = "APPLIQUÉ" if args.apply else "DRY-RUN (rollback en fin)"
    print(f"=== Patch consumable corrections — mode : {mode} ===")
    print(f"Base : {db_path}")

    backup_path: Path | None = None
    if args.apply and not args.no_backup:
        backup_path = backup(db_path)
        print(f"Sauvegarde créée : {backup_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        log = patch(conn, dry_run=not args.apply)
        for line in log:
            print(f"  {line}")
        if args.apply:
            conn.commit()
            print("\n✅ Modifications committées.")
        else:
            conn.rollback()
            print("\nℹ️  Dry-run : aucune modification écrite. Relancez avec --apply pour appliquer.")
    except Exception as exc:
        conn.rollback()
        print(f"\n❌ Erreur, rollback effectué : {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
