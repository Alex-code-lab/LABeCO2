"""
migrate_v3_end_of_life_factors.py

Migration v3 : ajoute les facteurs d'émission de fin de vie (incinération) issus
de l'ADEME Base Empreinte (v23.10 BC + v3.0 BI) et un cross-check Rizan 2021.

Après migration :
  - 3 nouvelles sources (ADEME BC v23.10, ADEME BI v3.0, Rizan 2021)
  - 8 nouveaux emission_factors avec factor_type='end_of_life'
  - Nouvelle colonne materials.eol_emission_factor_id (FK vers emission_factors)
  - 12 matériaux mappés vers leur facteur d'incinération
  - Métaux (Acier, Aluminium) laissés NULL : mâchefers récupérés à froid,
    pas d'émission directe. Le calculateur ignorera ces matériaux pour l'EoL.

Le routage NACRES → DASRI/DIS (déchets contaminés) est géré côté calculateur,
pas en base : voir ui/end_of_life.py (Phase 2).

Usage :
    python tools/migration/migrate_v3_end_of_life_factors.py
    python tools/migration/migrate_v3_end_of_life_factors.py --dry-run
    python tools/migration/migrate_v3_end_of_life_factors.py --db-path private/labeco2.sqlite
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "labeco2_reference.sqlite"
MIGRATION_VERSION = 3
MIGRATION_NAME = "add_end_of_life_factors"

# Contributeur "migration" (système) — déjà présent dans la base
MIGRATION_CONTRIBUTOR_ID = "6134f7a3-26c3-5820-b5ec-97147bf3536b"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _already_applied(conn: sqlite3.Connection) -> bool:
    try:
        cur = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (MIGRATION_VERSION,),
        )
        return cur.fetchone() is not None
    except sqlite3.OperationalError:
        return False


def _record_migration(conn: sqlite3.Connection, checksum: str) -> None:
    conn.execute(
        "INSERT INTO schema_migrations (version, name, applied_at, checksum) VALUES (?,?,?,?)",
        (
            MIGRATION_VERSION,
            MIGRATION_NAME,
            datetime.now(timezone.utc).isoformat(),
            checksum,
        ),
    )


def _stable_uuid(namespace: str, *parts: str) -> str:
    """UUID déterministe basé sur le contenu — idempotent."""
    key = "|".join(str(p) for p in parts)
    return str(uuid.uuid5(uuid.UUID(int=0), f"v3:{namespace}:{key}"))


def _name_key(name: str) -> str:
    """Clé normalisée (lowercase, trimée) — convention du schéma."""
    return name.strip().casefold()


# ── Données de référence ──────────────────────────────────────────────────────

# Sources (idempotentes via UUID déterministe sur title)
SOURCES = [
    {
        "title": "ADEME Base Empreinte v23.10 (Base Carbone)",
        "url": "https://base-empreinte.ademe.fr/",
        "doi": None,
        "citation": "ADEME — Base Empreinte®, jeu de données Base Carbone v23.10 (BC). "
                    "Facteurs maintenus par le GT Déchets Base Carbone.",
        "source_type": "ademe",
    },
    {
        "title": "ADEME Base Empreinte v3.0 (Base IMPACTS)",
        "url": "https://base-empreinte.ademe.fr/",
        "doi": None,
        "citation": "ADEME — Base Empreinte®, jeu de données Base IMPACTS v3.0 (BI). "
                    "Méthodologie PEF, rédigé par PE INTERNATIONAL / LBP-GaBi, "
                    "contributeur thinkstep AG.",
        "source_type": "ademe",
    },
    {
        "title": "Rizan et al. 2021 — Carbon footprint of waste streams in a UK hospital",
        "url": "https://doi.org/10.1016/j.jclepro.2020.125446",
        "doi": "10.1016/j.jclepro.2020.125446",
        "citation": "Rizan C, Bhutta MF, Reed M, Lillywhite R. (2021). The carbon footprint "
                    "of waste streams in a UK hospital. Journal of Cleaner Production, 286, 125446.",
        "source_type": "peer-reviewed",
    },
]

# Facteurs d'émission EoL (incinération)
# Tous les facteurs sont en kgCO2e/kg (normalisation depuis kgCO2e/t pour les fiches BC)
# uncertainty : taux d'incertitude relative (ex: 0.20 = ±20%). None si non publiée (fiches BI).
EOL_FACTORS = [
    # --- Filières déchets contaminés (routage NACRES côté code) ---
    {
        "name": "DAS/Incinération - Impacts (ADEME)",
        "co2_factor": 0.943,
        "uncertainty": 0.50,
        "source_title": "ADEME Base Empreinte v23.10 (Base Carbone)",
        "comment": "DASRI — Déchets d'Activités de Soins à Risque Infectieux. "
                   "Pour consommables de labos bio/santé (préfixes NACRES NB/NC/ND). "
                   "Qualité 1/5, à signaler dans l'UI.",
    },
    {
        "name": "DIS/Incinération - Impacts (ADEME)",
        "co2_factor": 0.844,
        "uncertainty": 0.20,
        "source_title": "ADEME Base Empreinte v23.10 (Base Carbone)",
        "comment": "DIS — Déchets Industriels Spéciaux (chimie). Pour consommables de "
                   "labos de chimie (préfixes NACRES NA/NL/NM). Qualité 3-4/5.",
    },
    # --- Plastiques (Base IMPACTS v3.0, peer-reviewed thinkstep/GaBi) ---
    {
        "name": "Incinération - Déchets en plastique, FR (ADEME)",
        "co2_factor": 2.27,
        "uncertainty": None,
        "source_title": "ADEME Base Empreinte v3.0 (Base IMPACTS)",
        "comment": "Facteur générique tout-plastique. Fallback pour matériaux sans "
                   "fiche spécifique (PC, PMMA, PTFE, nitrile…). Qualité PEF 5/5.",
    },
    {
        "name": "Incinération - Plastique (PE, PP; PB, PS), FR (ADEME)",
        "co2_factor": 3.04,
        "uncertainty": None,
        "source_title": "ADEME Base Empreinte v3.0 (Base IMPACTS)",
        "comment": "Polyoléfines pétrosourcées. Couvre PE, PP, PB, PS. Qualité PEF 5/5.",
    },
    {
        "name": "Incinération - Plastique (PVC rigide), FR (ADEME)",
        "co2_factor": 2.25,
        "uncertainty": None,
        "source_title": "ADEME Base Empreinte v3.0 (Base IMPACTS)",
        "comment": "PVC rigide pétrosourcé. Valeur plus faible que PE/PP car le Cl "
                   "réduit la fraction carbone. Qualité PEF 5/5.",
    },
    {
        "name": "Incinération - Déchets en verre, FR (ADEME)",
        "co2_factor": 0.0541,
        "uncertainty": None,
        "source_title": "ADEME Base Empreinte v3.0 (Base IMPACTS)",
        "comment": "Verre conventionnel et borosilicate. Le verre ne brûle pas → facteur "
                   "très faible (énergie process + transport seulement). Qualité PEF 5/5. "
                   "NE PAS confondre avec la fiche BC Emballages/Verre (0.130) qui "
                   "surévalue d'un facteur 2.4 (allocation par masse).",
    },
    # --- Emballages spécifiques (Base Carbone v23.10) ---
    {
        "name": "Emballages/Carton/Incinération - Impacts (ADEME)",
        "co2_factor": 0.120,
        "uncertainty": 0.20,
        "source_title": "ADEME Base Empreinte v23.10 (Base Carbone)",
        "comment": "Carton & papier en filière banale triée. Couvre aussi le papier "
                   "(proxy). Qualité 3/5.",
    },
    {
        "name": "Emballages/Plastique pétrosourcé PET/Incinération - Impacts (ADEME)",
        "co2_factor": 2.14,
        "uncertainty": 0.20,
        "source_title": "ADEME Base Empreinte v23.10 (Base Carbone)",
        "comment": "PET pétrosourcé. Utilisé en attendant une fiche BI v3.0 dédiée. "
                   "Qualité 3/5.",
    },
]

# Mapping matériau (name dans table materials) → nom du facteur EoL
# Les matériaux non listés (Acier, Aluminium) restent NULL.
MATERIAL_EOL_MAPPING: dict[str, str] = {
    "Carton":                            "Emballages/Carton/Incinération - Impacts (ADEME)",
    "Papier":                            "Emballages/Carton/Incinération - Impacts (ADEME)",
    "Verre":                             "Incinération - Déchets en verre, FR (ADEME)",
    "Polyéthylène (PE)":                 "Incinération - Plastique (PE, PP; PB, PS), FR (ADEME)",
    "Polypropylène (PP)":                "Incinération - Plastique (PE, PP; PB, PS), FR (ADEME)",
    "Polystyrène (PS)":                  "Incinération - Plastique (PE, PP; PB, PS), FR (ADEME)",
    "Polyéthylène téréphtalate (PET)":   "Emballages/Plastique pétrosourcé PET/Incinération - Impacts (ADEME)",
    "Polychlorure de vinyle (PVC)":      "Incinération - Plastique (PVC rigide), FR (ADEME)",
    "Polycarbonate (PC)":                "Incinération - Déchets en plastique, FR (ADEME)",
    "Polyméthacrylate de méthyle (PMMA)":"Incinération - Déchets en plastique, FR (ADEME)",
    "Polytétrafluoroéthylène (PTFE)":    "Incinération - Déchets en plastique, FR (ADEME)",
    "Nitrile":                           "Incinération - Déchets en plastique, FR (ADEME)",
    # Métaux : NULL — les mâchefers sont récupérés à froid, pas d'émission directe.
    # "Acier inoxydable": None,
    # "Aluminium": None,
}


# ── Migration ─────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, db_path: Path | None = None) -> None:
    target_db = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    if not target_db.exists():
        print(f"ERREUR : base introuvable à {target_db}")
        return

    print(f"Base ciblée : {target_db}")
    conn = sqlite3.connect(target_db)
    conn.row_factory = sqlite3.Row

    if _already_applied(conn):
        print(f"Migration v{MIGRATION_VERSION} déjà appliquée — rien à faire.")
        conn.close()
        return

    # Backup
    backup = target_db.with_suffix(f".pre_v{MIGRATION_VERSION}.backup")
    if not dry_run:
        shutil.copy2(target_db, backup)
        print(f"Backup → {backup.name}")

    now = datetime.now(timezone.utc).isoformat()

    try:
        conn.execute("BEGIN")

        # ── 1. Insérer les sources ─────────────────────────────────────────
        source_id_by_title: dict[str, str] = {}
        sources_inserted = 0
        for src in SOURCES:
            sid = _stable_uuid("source", src["title"])
            source_id_by_title[src["title"]] = sid
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO sources
                    (id, title, url, doi, citation, source_type,
                     contributor_id, created_at, updated_at, status)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sid, src["title"], src["url"], src["doi"],
                    src["citation"], src["source_type"],
                    MIGRATION_CONTRIBUTOR_ID, now, now, "validated",
                ),
            )
            sources_inserted += cur.rowcount
        print(f"  ✓ {sources_inserted} sources insérées (sur {len(SOURCES)})")

        # ── 2. Insérer les facteurs EoL ────────────────────────────────────
        factor_id_by_name: dict[str, str] = {}
        factors_inserted = 0
        for f in EOL_FACTORS:
            fid = _stable_uuid("eol_factor", f["name"])
            factor_id_by_name[f["name"]] = fid
            src_id = source_id_by_title[f["source_title"]]
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO emission_factors
                    (id, name, name_key, factor_type, co2_factor, co2_unit,
                     uncertainty, source_id, contributor_id,
                     created_at, updated_at, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    fid, f["name"], _name_key(f["name"]),
                    "end_of_life", f["co2_factor"], "kg CO2e/kg",
                    f["uncertainty"], src_id, MIGRATION_CONTRIBUTOR_ID,
                    now, now, "validated",
                ),
            )
            factors_inserted += cur.rowcount
        print(f"  ✓ {factors_inserted} facteurs EoL insérés (sur {len(EOL_FACTORS)})")

        # ── 3. Ajouter la colonne materials.eol_emission_factor_id ─────────
        existing_cols = _columns(conn, "materials")
        if "eol_emission_factor_id" not in existing_cols:
            conn.execute(
                "ALTER TABLE materials ADD COLUMN eol_emission_factor_id TEXT "
                "REFERENCES emission_factors(id)"
            )
            print("  ✓ Colonne materials.eol_emission_factor_id ajoutée")
        else:
            print("  ~ Colonne materials.eol_emission_factor_id déjà présente")

        # ── 4. Mapper les matériaux vers leur facteur EoL ──────────────────
        mapped = 0
        unmatched_materials: list[str] = []
        unmatched_factors: list[str] = []
        for mat_name, factor_name in MATERIAL_EOL_MAPPING.items():
            fid = factor_id_by_name.get(factor_name)
            if fid is None:
                unmatched_factors.append(factor_name)
                continue
            cur = conn.execute(
                "UPDATE materials SET eol_emission_factor_id = ?, updated_at = ? "
                "WHERE name = ? AND (eol_emission_factor_id IS NULL OR eol_emission_factor_id = '')",
                (fid, now, mat_name),
            )
            if cur.rowcount == 0:
                # Soit le matériau n'existe pas, soit il a déjà un facteur
                check = conn.execute(
                    "SELECT 1 FROM materials WHERE name = ?", (mat_name,)
                ).fetchone()
                if check is None:
                    unmatched_materials.append(mat_name)
            else:
                mapped += cur.rowcount

        print(f"  ✓ {mapped} matériaux mappés vers leur facteur EoL")
        if unmatched_materials:
            print(f"  ⚠ Matériaux non trouvés en base : {unmatched_materials}")
        if unmatched_factors:
            print(f"  ⚠ Facteurs introuvables : {unmatched_factors}")

        # Récap : combien de matériaux ont (ou pas) un EoL ?
        with_eol = conn.execute(
            "SELECT COUNT(*) FROM materials WHERE eol_emission_factor_id IS NOT NULL"
        ).fetchone()[0]
        without_eol_rows = conn.execute(
            "SELECT name FROM materials WHERE eol_emission_factor_id IS NULL ORDER BY name"
        ).fetchall()
        without_eol = [r[0] for r in without_eol_rows]
        print(f"  ℹ Matériaux avec EoL : {with_eol} • sans EoL : {len(without_eol)} → {without_eol}")

        # ── 5. Enregistrer la migration ────────────────────────────────────
        payload = (
            "|".join(src["title"] for src in SOURCES) + "||" +
            "|".join(f["name"] for f in EOL_FACTORS) + "||" +
            "|".join(f"{m}={f}" for m, f in MATERIAL_EOL_MAPPING.items())
        )
        checksum = hashlib.sha256(payload.encode()).hexdigest()[:16]
        _record_migration(conn, checksum)

        if dry_run:
            conn.execute("ROLLBACK")
            print("\nDRY-RUN : aucune modification appliquée.")
        else:
            conn.execute("COMMIT")
            print(f"\nMigration v{MIGRATION_VERSION} appliquée avec succès.")

    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"ERREUR : {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Simuler sans modifier la base")
    parser.add_argument("--db-path", default=None,
                        help="Chemin SQLite cible (par défaut : data/labeco2_reference.sqlite)")
    args = parser.parse_args()
    run(dry_run=args.dry_run, db_path=args.db_path)
