# SPDX-License-Identifier: GPL-3.0-or-later
"""Analyse sûre des fusions de bases/contributions LABeCO2."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.contribution_io import TABLES_ORDER, diff_rows
from tools.admin.workflow import NON_FINAL_STATUSES, VALIDATED, clean, normalized_key


MERGE_TABLES = TABLES_ORDER
IMPORTABLE_KINDS = {"NOUVEAU", "DEPENDANCE"}
MANUAL_DECISION_KINDS = {
    "CONFLIT_ID",
    "DOUBLON_METIER",
    "NON_VALIDE_DES_DEUX_COTES",
    "REVISION_POSSIBLE",
}


@dataclass(frozen=True)
class MergeClassification:
    kind: str
    table: str
    row_id: str
    data: dict
    existing: dict
    diffs: list[str]
    business_key: str = ""
    reason: str = ""

    def to_entry(self) -> dict:
        return {
            "kind": self.kind,
            "table": self.table,
            "id": self.row_id,
            "data": self.data,
            "existing": self.existing,
            "diffs": self.diffs,
            "business_key": self.business_key,
            "reason": self.reason,
        }


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone() is not None


def rows_as_dict(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    conn.row_factory = sqlite3.Row
    if not table_exists(conn, table):
        return {}
    return {row["id"]: dict(row) for row in conn.execute(f"SELECT * FROM {table}")}


def sqlite_index(path: Path) -> dict[str, dict[str, dict]]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return {table: rows_as_dict(conn, table) for table in MERGE_TABLES}
    finally:
        conn.close()


def payload_index(payload: dict) -> dict[str, dict[str, dict]]:
    index: dict[str, dict[str, dict]] = {table: {} for table in MERGE_TABLES}
    for table in ("sources", "contributors"):
        for row in payload.get(table, []):
            if row.get("id"):
                index[table][row["id"]] = row
    for entry in payload.get("entries", []):
        table = entry.get("table")
        data = entry.get("data", {})
        if table in index and data.get("id"):
            index[table][data["id"]] = data
    return index


def business_key(table: str, row: dict[str, Any]) -> str:
    if table == "commercial_products":
        reference = clean(row.get("reference"))
        if reference:
            return f"reference:{normalized_key(reference)}"
        return "product:" + normalized_key(
            row.get("brand"),
            row.get("name"),
            row.get("sold_packaging_label"),
            row.get("code_nacres"),
        )
    if table == "emission_factors":
        return "factor:" + normalized_key(
            row.get("factor_type"),
            row.get("name_key") or row.get("name"),
            row.get("code_nacres"),
        )
    if table == "materials":
        return "material:" + normalized_key(row.get("name_key") or row.get("name"))
    if table == "transport_factors":
        return "transport:" + normalized_key(row.get("origin"), row.get("mode"), row.get("distance_km"))
    if table == "sources":
        doi = clean(row.get("doi"))
        url = clean(row.get("url"))
        if doi:
            return f"doi:{normalized_key(doi)}"
        if url:
            return f"url:{normalized_key(url)}"
        return "source:" + normalized_key(row.get("title"))
    if table == "contributors":
        email = clean(row.get("email"))
        if email:
            return f"email:{normalized_key(email)}"
        return "contributor:" + normalized_key(row.get("name"))
    if table == "product_components":
        return "component:" + normalized_key(
            row.get("product_id"),
            row.get("component_type"),
            row.get("material_id"),
            row.get("units_divisor"),
        )
    return ""


def business_indexes(index: dict[str, dict[str, dict]]) -> dict[str, dict[str, list[dict]]]:
    result: dict[str, dict[str, list[dict]]] = {}
    for table, rows in index.items():
        table_index: dict[str, list[dict]] = {}
        for row in rows.values():
            key = business_key(table, row)
            if key:
                table_index.setdefault(key, []).append(row)
        result[table] = table_index
    return result


def _status(row: dict) -> str:
    return clean(row.get("status"))


def _classify_conflict(table: str, data: dict, existing: dict, diffs: list[str], key: str, *, same_id: bool) -> MergeClassification:
    row_id = clean(data.get("id"))
    data_status = _status(data)
    existing_status = _status(existing)
    if data_status in NON_FINAL_STATUSES and existing_status in NON_FINAL_STATUSES:
        return MergeClassification(
            "NON_VALIDE_DES_DEUX_COTES",
            table,
            row_id,
            data,
            existing,
            diffs,
            key,
            "Deux versions non validées existent; résolution manuelle obligatoire.",
        )
    if existing_status == VALIDATED:
        return MergeClassification(
            "REVISION_POSSIBLE",
            table,
            row_id,
            data,
            existing,
            diffs,
            key,
            "Une entrée validée existe déjà; créer une révision ou résoudre manuellement.",
        )
    return MergeClassification(
        "CONFLIT_ID" if same_id else "DOUBLON_METIER",
        table,
        row_id,
        data,
        existing,
        diffs,
        key,
        "Même identifiant avec différences." if same_id else "Même clé métier avec identifiant différent.",
    )


def classify_row(
    table: str,
    data: dict,
    ref_index: dict[str, dict[str, dict]],
    ref_business_index: dict[str, dict[str, list[dict]]] | None = None,
) -> MergeClassification:
    row_id = clean(data.get("id"))
    key = business_key(table, data)
    existing_by_id = ref_index.get(table, {}).get(row_id)
    if existing_by_id is not None:
        diffs = diff_rows(existing_by_id, data)
        if not diffs:
            return MergeClassification("IDENTIQUE", table, row_id, data, existing_by_id, [], key, "Entrée identique.")
        return _classify_conflict(table, data, existing_by_id, diffs, key, same_id=True)

    ref_business_index = ref_business_index or business_indexes(ref_index)
    candidates = ref_business_index.get(table, {}).get(key, []) if key else []
    if candidates:
        existing = candidates[0]
        diffs = diff_rows(existing, data)
        if not diffs:
            diffs = [f"  ID existant : {existing.get('id')}"]
        return _classify_conflict(table, data, existing, diffs, key, same_id=False)

    return MergeClassification("NOUVEAU", table, row_id, data, {}, [], key, "Absente de la référence.")


def classify_index(
    source_index: dict[str, dict[str, dict]],
    ref_index: dict[str, dict[str, dict]],
    *,
    tables: list[str] | None = None,
    include_identical: bool = False,
) -> list[MergeClassification]:
    selected = tables or MERGE_TABLES
    ref_business = business_indexes(ref_index)
    results: list[MergeClassification] = []
    for table in selected:
        for data in source_index.get(table, {}).values():
            classification = classify_row(table, data, ref_index, ref_business)
            if include_identical or classification.kind != "IDENTIQUE":
                results.append(classification)
    return results


def importable_entries(entries: list[dict]) -> list[dict]:
    return [entry for entry in entries if entry.get("kind") in IMPORTABLE_KINDS]


def blocked_entries(entries: list[dict]) -> list[dict]:
    return [entry for entry in entries if entry.get("kind") not in IMPORTABLE_KINDS]

