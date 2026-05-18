# SPDX-License-Identifier: GPL-3.0-or-later
"""Opérations SQLite communes pour la validation administrative."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_entry(
    conn: sqlite3.Connection,
    table: str,
    entry_id: str,
    validator_id: str,
    dry_run: bool = False,
) -> None:
    if dry_run:
        return
    now = now_iso()
    conn.execute(
        f"""UPDATE {table}
            SET status = 'validated', validated_by_id = ?, validated_at = ?, updated_at = ?
            WHERE id = ?""",
        (validator_id, now, now, entry_id),
    )


def reject_entry(
    conn: sqlite3.Connection,
    table: str,
    entry_id: str,
    dry_run: bool = False,
) -> None:
    if dry_run:
        return
    now = now_iso()
    conn.execute(
        f"""UPDATE {table}
            SET status = 'deprecated', deprecated_at = ?, updated_at = ?
            WHERE id = ?""",
        (now, now, entry_id),
    )


def reject_liquid_orphans(
    conn: sqlite3.Connection,
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    orphans = conn.execute("""
        SELECT id, name FROM commercial_products
        WHERE product_type = 'liquid'
          AND (emission_factor_id IS NULL OR emission_factor_id = '')
          AND status != 'deprecated'
    """).fetchall()
    for row in orphans:
        reject_entry(conn, "commercial_products", row[0], dry_run=dry_run)
    return [(row[0], row[1]) for row in orphans]
