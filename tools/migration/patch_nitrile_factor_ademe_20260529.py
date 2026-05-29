# SPDX-License-Identifier: GPL-3.0-or-later
"""Met à jour le facteur d'émission Nitrile sur la source ADEME NBR (29 mai 2026).

Contexte :
    L'ancienne valeur (6.4 kg CO2e/kg) provenait du papier Ragazzi 2023
    (DOI : 10.1371/journal.pstr.0000080), qui sert aussi de base à PER1p5.
    Cette circularité de source biaisait les comparaisons de validation.

    Le facteur ADEME Base Empreinte v3.0 (Base IMPACTS) "Caoutchouc
    Nitrile-Butadiène (NBR), RER" donne 5.44 kg CO2e/kg — valeur plus
    cohérente avec les ACV indépendantes (PER1p5 ~ 78 g par paire de gants
    13 g vs LABeCO2 ~ 83 g, écart résiduel < 7 %).

Changements :
    - co2_factor : 6.4 → 5.44 kg CO2e/kg
    - name : "Nitrile" → "Caoutchouc Nitrile-Butadiène (NBR)"
    - source : Ragazzi 2023 → ADEME Base Empreinte v3.0 (Base IMPACTS)
    - uncertainty : reste à 0.2 (incertitude ADEME non publiée mais
      cohérente avec les autres matériaux Base IMPACTS)

Usage :
    python tools/migration/patch_nitrile_factor_ademe_20260529.py             # dry-run
    python tools/migration/patch_nitrile_factor_ademe_20260529.py --apply
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

NEW_FACTOR_NAME = "Caoutchouc Nitrile-Butadiène (NBR)"
NEW_CO2 = 5.44
NEW_UNCERTAINTY = 0.2
NEW_SOURCE_TITLE = "ADEME Base Empreinte v3.0 (Base IMPACTS)"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def backup(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = db_path.with_name(f"{db_path.name}.backup_before_patch_{stamp}")
    shutil.copy2(db_path, target)
    return target


def patch(conn: sqlite3.Connection) -> list[str]:
    log: list[str] = []
    now = now_iso()

    # 1. Récupère le facteur Nitrile actuel
    conn.row_factory = sqlite3.Row
    ef = conn.execute(
        """
        SELECT id, name, co2_factor, source_id
        FROM emission_factors
        WHERE name = 'Nitrile' AND COALESCE(status, '') != 'deprecated'
        LIMIT 1
        """
    ).fetchone()
    if not ef:
        raise RuntimeError("Facteur 'Nitrile' introuvable en base.")
    log.append(f"Facteur actuel : id={ef['id'][:8]}…  '{ef['name']}'  {ef['co2_factor']} kgCO2e/kg")

    # 2. Récupère l'ID de la source ADEME Base IMPACTS
    source = conn.execute(
        "SELECT id, title FROM sources WHERE title = ? LIMIT 1",
        (NEW_SOURCE_TITLE,),
    ).fetchone()
    if not source:
        raise RuntimeError(f"Source '{NEW_SOURCE_TITLE}' introuvable.")
    log.append(f"Nouvelle source : id={source['id'][:8]}…  '{source['title']}'")

    # 3. Update — nom, facteur, source, updated_at
    conn.execute(
        """
        UPDATE emission_factors
        SET name = ?,
            co2_factor = ?,
            uncertainty = ?,
            source_id = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (NEW_FACTOR_NAME, NEW_CO2, NEW_UNCERTAINTY, source["id"], now, ef["id"]),
    )
    log.append(
        f"UPDATE : name → '{NEW_FACTOR_NAME}'  |  "
        f"co2_factor {ef['co2_factor']} → {NEW_CO2}  |  uncertainty=±{NEW_UNCERTAINTY}"
    )

    # 4. Vérifie combien de matériaux référencent ce facteur
    n_mats = conn.execute(
        "SELECT COUNT(*) FROM materials WHERE emission_factor_id = ?",
        (ef["id"],),
    ).fetchone()[0]
    log.append(f"Matériaux impactés : {n_mats} (recalcul automatique au prochain accès)")

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
    print(f"=== Patch Nitrile → ADEME NBR — mode : {mode} ===")
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
