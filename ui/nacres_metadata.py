# SPDX-License-Identifier: GPL-3.0-or-later
"""Lecture des métadonnées NACRES depuis SQLite."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


NACRES_STATUS_NEW = "nouveau"


@dataclass(frozen=True)
class NacresOption:
    code: str
    label: str
    statut_maj_2026: str
    has_purchase_factor: bool

    @property
    def is_new_without_labo1point5_fe(self) -> bool:
        return self.statut_maj_2026 == NACRES_STATUS_NEW and not self.has_purchase_factor


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def load_nacres_options(conn: sqlite3.Connection) -> list[NacresOption]:
    """Retourne les vrais codes NACRES détaillés, enrichis avec leur statut 2026."""
    nacres_columns = _columns(conn, "nacres_codes")
    status_expr = (
        "COALESCE(n.statut_maj_2026, '')"
        if "statut_maj_2026" in nacres_columns
        else "''"
    )
    rows = conn.execute(
        f"""
        SELECT
            n.code,
            COALESCE(n.label, '') AS label,
            {status_expr} AS statut_maj_2026,
            EXISTS (
                SELECT 1
                FROM purchase_factors p
                WHERE p.category = 'Achats'
                  AND UPPER(SUBSTR(TRIM(p.subsubcategory), 1, 4)) = UPPER(n.code)
            ) AS has_purchase_factor
        FROM nacres_codes n
        WHERE n.code GLOB '[A-Z][A-Z][0-9][0-9]'
        ORDER BY n.code
        """
    ).fetchall()
    return [
        NacresOption(
            code=str(row[0] or "").strip().upper(),
            label=str(row[1] or "").strip(),
            statut_maj_2026=str(row[2] or "").strip(),
            has_purchase_factor=bool(row[3]),
        )
        for row in rows
    ]
