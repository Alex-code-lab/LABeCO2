# SPDX-License-Identifier: GPL-3.0-or-later
"""Transitions métier du cycle admin LABeCO2."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from tools.admin.quality_rules import (
    DEPRECATED,
    DRAFT,
    PENDING,
    VALIDATED,
    QualityIssue,
    blocking_issues,
    check_entries_quality,
    check_entry_quality,
    clean,
    format_admin_issues,
    normalized_key,
)
from ui.sqlite_schema import ensure_app_schema


NON_FINAL_STATUSES = {PENDING, DRAFT}
FINAL_STATUSES = {VALIDATED, DEPRECATED}

# Compatibilité avec le reste de l'admin : l'ancien nom AdminIssue pointe
# maintenant vers l'anomalie qualité commune.
AdminIssue = QualityIssue


@dataclass
class PromotionResult:
    promoted: list[str]
    blocked: dict[str, list[AdminIssue]]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def promotable_pending_products(
    conn: sqlite3.Connection,
    product_ids: Iterable[str] | None = None,
) -> PromotionResult:
    ensure_app_schema(conn)
    ids = set(product_ids or [])
    params: list[str] = []
    where = "WHERE status = 'pending'"
    if ids:
        placeholders = ",".join("?" * len(ids))
        where += f" AND id IN ({placeholders})"
        params.extend(sorted(ids))

    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"SELECT * FROM commercial_products {where}", params).fetchall()
    promoted: list[str] = []
    blocked: dict[str, list[AdminIssue]] = {}
    for row_obj in rows:
        row = dict(row_obj)
        issues = blocking_issues(check_entry_quality(conn, "commercial_products", row))
        if issues:
            blocked[row["id"]] = issues
        else:
            promoted.append(row["id"])
    return PromotionResult(promoted=promoted, blocked=blocked)


def promote_pending_products(
    conn: sqlite3.Connection,
    product_ids: Iterable[str] | None = None,
) -> PromotionResult:
    result = promotable_pending_products(conn, product_ids)
    if result.promoted:
        now = now_iso()
        conn.executemany(
            "UPDATE commercial_products SET status = 'draft', updated_at = ? WHERE id = ?",
            [(now, product_id) for product_id in result.promoted],
        )
    return result


def format_issues(issues: Iterable[AdminIssue], *, max_items: int = 12) -> str:
    return format_admin_issues(issues, max_items=max_items)


__all__ = [
    "AdminIssue",
    "DEPRECATED",
    "DRAFT",
    "FINAL_STATUSES",
    "NON_FINAL_STATUSES",
    "PENDING",
    "PromotionResult",
    "VALIDATED",
    "blocking_issues",
    "check_entries_quality",
    "check_entry_quality",
    "clean",
    "format_issues",
    "normalized_key",
    "now_iso",
    "promotable_pending_products",
    "promote_pending_products",
]
