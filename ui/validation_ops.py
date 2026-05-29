# SPDX-License-Identifier: GPL-3.0-or-later
"""Opérations SQLite communes pour la validation administrative."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Iterable


_WRITABLE_TABLES = frozenset({
    "emission_factors",
    "materials",
    "commercial_products",
    "transport_factors",
    "sources",
    "contributors",
})


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _check_table(table: str) -> None:
    if table not in _WRITABLE_TABLES:
        raise ValueError(f"Table non autorisée pour la validation : {table}")


def validate_entry(
    conn: sqlite3.Connection,
    table: str,
    entry_id: str,
    validator_id: str,
    dry_run: bool = False,
) -> None:
    if dry_run:
        return
    _check_table(table)
    now = now_iso()
    conn.execute(
        f"""UPDATE {table}
            SET status = 'validated', validated_by_id = ?, validated_at = ?, updated_at = ?
            WHERE id = ?""",
        (validator_id, now, now, entry_id),
    )


def validate_entries(
    conn: sqlite3.Connection,
    entries: Iterable[tuple[str, str]],
    validator_id: str,
    dry_run: bool = False,
) -> int:
    """Valide plusieurs entrées en groupant les écritures par table."""
    if dry_run:
        return 0
    by_table: dict[str, list[str]] = {}
    for table, entry_id in entries:
        _check_table(table)
        by_table.setdefault(table, []).append(entry_id)

    now = now_iso()
    total = 0
    for table, ids in by_table.items():
        conn.executemany(
            f"""UPDATE {table}
                SET status = 'validated', validated_by_id = ?, validated_at = ?, updated_at = ?
                WHERE id = ?""",
            [(validator_id, now, now, entry_id) for entry_id in ids],
        )
        total += len(ids)
    return total


def reject_entry(
    conn: sqlite3.Connection,
    table: str,
    entry_id: str,
    dry_run: bool = False,
) -> None:
    if dry_run:
        return
    _check_table(table)
    now = now_iso()
    conn.execute(
        f"""UPDATE {table}
            SET status = 'deprecated', deprecated_at = ?, updated_at = ?
            WHERE id = ?""",
        (now, now, entry_id),
    )


def reject_entries(
    conn: sqlite3.Connection,
    entries: Iterable[tuple[str, str]],
    dry_run: bool = False,
) -> int:
    """Déprécie plusieurs entrées en groupant les écritures par table."""
    if dry_run:
        return 0
    by_table: dict[str, list[str]] = {}
    for table, entry_id in entries:
        _check_table(table)
        by_table.setdefault(table, []).append(entry_id)

    now = now_iso()
    total = 0
    for table, ids in by_table.items():
        conn.executemany(
            f"""UPDATE {table}
                SET status = 'deprecated', deprecated_at = ?, updated_at = ?
                WHERE id = ?""",
            [(now, now, entry_id) for entry_id in ids],
        )
        total += len(ids)
    return total


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
