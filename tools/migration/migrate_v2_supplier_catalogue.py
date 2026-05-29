"""
migrate_v2_supplier_catalogue.py

Migration v2 : crée la table générique `supplier_catalogue` et y migre les
données existantes de `catalogue_ijm`.

Après migration :
  - supplier_catalogue  contient tous les tarifs fournisseurs (IJM + futurs)
  - commercial_products.supplier_catalogue_id  pointe vers supplier_catalogue
  - catalogue_ijm et ijm_catalogue_id sont conservés (aucun code existant cassé)

Usage :
    python tools/migration/migrate_v2_supplier_catalogue.py
    python tools/migration/migrate_v2_supplier_catalogue.py --dry-run
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
DB_PATH = ROOT / "data" / "labeco2_reference.sqlite"
MIGRATION_VERSION = 2
MIGRATION_NAME = "add_supplier_catalogue_generic_table"


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
    return str(uuid.uuid5(uuid.UUID(int=0), f"{namespace}:{key}"))


# ── SQL ────────────────────────────────────────────────────────────────────────

CREATE_SUPPLIER_CATALOGUE = """
CREATE TABLE IF NOT EXISTS supplier_catalogue (
    id                TEXT PRIMARY KEY,
    supplier          TEXT NOT NULL,
    catalogue_date    TEXT,
    code_fournisseur  TEXT,
    designation       TEXT,
    brand             TEXT,
    conditionnement   TEXT,
    price_ht          REAL,
    units_per_pack    INTEGER,
    mass_g            REAL,
    volume_ml         REAL,
    imported_at       TEXT
);
"""

MIGRATION_SQL = """
-- Étape 1 : table supplier_catalogue
{create_table}

-- Étape 2 : colonne supplier_catalogue_id dans commercial_products
-- (ALTER TABLE IF NOT EXISTS n'existe pas en SQLite, géré en Python)
"""


# ── Inférence masse / volume ───────────────────────────────────────────────────

import re

_UNIT_RE = re.compile(
    r'([\d,\.]+)\s*'
    r'(kg|mg|g\b|litre?s?|l\b|ml|µl|µg|iu|u\b)',
    re.IGNORECASE,
)


def infer_mass_volume(conditionnement: str) -> tuple[float | None, float | None]:
    """
    Retourne (mass_g, volume_ml) depuis une chaîne de conditionnement.
    Ex : "25 g" → (25.0, None), "1 kg" → (1000.0, None), "100 ml" → (None, 100.0)
    """
    if not conditionnement:
        return None, None

    s = conditionnement.strip()
    m = _UNIT_RE.search(s)
    if not m:
        return None, None

    qty = float(m.group(1).replace(',', '.'))
    unit = m.group(2).lower()

    if unit == 'kg':
        return qty * 1000, None
    if unit == 'g':
        return qty, None
    if unit == 'mg':
        return qty / 1000, None
    if unit == 'µg':
        return qty / 1_000_000, None
    if unit in ('l', 'litre', 'litres'):
        return None, qty * 1000
    if unit == 'ml':
        return None, qty
    if unit == 'µl':
        return None, qty / 1000

    return None, None


# ── Migration ─────────────────────────────────────────────────────────────────

def run(dry_run: bool = False) -> None:
    if not DB_PATH.exists():
        print(f"ERREUR : base introuvable à {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if _already_applied(conn):
        print(f"Migration v{MIGRATION_VERSION} déjà appliquée — rien à faire.")
        conn.close()
        return

    # Backup
    backup = DB_PATH.with_suffix(f".pre_v{MIGRATION_VERSION}.backup")
    if not dry_run:
        shutil.copy2(DB_PATH, backup)
        print(f"Backup → {backup.name}")

    now = datetime.now(timezone.utc).isoformat()

    try:
        conn.execute("BEGIN")

        # ── 1. Créer supplier_catalogue ────────────────────────────────────
        conn.execute(CREATE_SUPPLIER_CATALOGUE)
        print("  ✓ Table supplier_catalogue créée")

        # ── 2. Copier catalogue_ijm → supplier_catalogue ───────────────────
        rows_ijm = conn.execute("SELECT * FROM catalogue_ijm").fetchall()
        inserted = 0
        ijm_id_map: dict[str, str] = {}  # catalogue_ijm.id → supplier_catalogue.id

        for row in rows_ijm:
            new_id = _stable_uuid("supplier_catalogue", "IJM", row["id"])
            mass_g, volume_ml = infer_mass_volume(row["conditionnement"] or "")
            conn.execute(
                """
                INSERT OR IGNORE INTO supplier_catalogue
                    (id, supplier, catalogue_date, code_fournisseur, designation,
                     brand, conditionnement, price_ht, units_per_pack,
                     mass_g, volume_ml, imported_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    new_id, "IJM", "2025",
                    row["code_ijm"], row["designation"],
                    row["brand"], row["conditionnement"],
                    row["price_ht"], row["units_per_pack"],
                    mass_g, volume_ml,
                    row["imported_at"] or now,
                ),
            )
            ijm_id_map[row["id"]] = new_id
            inserted += 1

        print(f"  ✓ {inserted} lignes IJM copiées dans supplier_catalogue")

        # ── 3. Ajouter supplier_catalogue_id dans commercial_products ──────
        existing_cols = _columns(conn, "commercial_products")
        if "supplier_catalogue_id" not in existing_cols:
            conn.execute(
                "ALTER TABLE commercial_products ADD COLUMN supplier_catalogue_id TEXT"
            )
            print("  ✓ Colonne supplier_catalogue_id ajoutée à commercial_products")
        else:
            print("  ~ Colonne supplier_catalogue_id déjà présente")

        # ── 4. Peupler supplier_catalogue_id depuis ijm_catalogue_id ──────
        updated = 0
        for old_id, new_id in ijm_id_map.items():
            cur = conn.execute(
                """
                UPDATE commercial_products
                SET supplier_catalogue_id = ?
                WHERE ijm_catalogue_id = ? AND supplier_catalogue_id IS NULL
                """,
                (new_id, old_id),
            )
            updated += cur.rowcount

        print(f"  ✓ {updated} commercial_products liés à supplier_catalogue")

        # ── 5. Enregistrer la migration ────────────────────────────────────
        checksum = hashlib.sha256(CREATE_SUPPLIER_CATALOGUE.encode()).hexdigest()[:16]
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
    args = parser.parse_args()
    run(dry_run=args.dry_run)
