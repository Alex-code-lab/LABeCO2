# SPDX-License-Identifier: GPL-3.0-or-later
"""
LABeCO2 — Outil d'administration des bases de données.

Lance une application Qt indépendante avec trois onglets :
  1. Validation   — valider ou rejeter les entrées draft
  2. Fusion       — fusionner deux bases SQLite, résoudre les conflits
  3. Qualité      — audit complet de la base

Usage :
    python tools/lab_admin.py [--db PATH]
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from tools.contribution_io import (
    TABLES_ORDER,
    apply_contribution_entries,
    diff_rows,
    import_dependencies,
    load_contribution_payload,
)
from ui.validate_window import ValidateWidget
from ui.quality_check import check_database


# ============================================================
# Onglet 1 — Validation
# ============================================================

class ValidationTab(QWidget):
    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = db_path
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._widget = ValidateWidget(db_path, show_close=False, parent=self)
        layout.addWidget(self._widget)

    def reload(self, db_path: Path) -> None:
        self.db_path = db_path
        self._widget.sqlite_path = db_path
        self._widget._load_table()


# ============================================================
# Onglet 2 — Fusion / Conflits
# ============================================================

_MERGE_TABLES = TABLES_ORDER
_CONTEXT_TABLES = TABLES_ORDER
_TABLE_LABEL = {
    "contributors": "Contributeurs",
    "sources": "Sources",
    "emission_factors": "Facteurs d'émission",
    "materials": "Matériaux",
    "commercial_products": "Consommables",
    "product_components": "Composants",
    "transport_factors": "Transport",
}
_NAME_COL = {
    "emission_factors": "name",
    "materials": "name",
    "commercial_products": "name",
    "sources": "title",
    "contributors": "name",
    "transport_factors": "origin",
}

_SEV_COLOR = {
    "NOUVEAU":   QColor(213, 245, 213),
    "CONFLIT":   QColor(255, 243, 178),
    "DOUBLON":   QColor(255, 220, 180),
}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone() is not None


def _rows_as_dict(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    conn.row_factory = sqlite3.Row
    if not _table_exists(conn, table):
        return {}
    return {r["id"]: dict(r) for r in conn.execute(f"SELECT * FROM {table}")}


def _sqlite_index(path: Path) -> dict[str, dict[str, dict]]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return {table: _rows_as_dict(conn, table) for table in _CONTEXT_TABLES}
    finally:
        conn.close()


def _payload_index(payload: dict) -> dict[str, dict[str, dict]]:
    index: dict[str, dict[str, dict]] = {table: {} for table in _CONTEXT_TABLES}
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


def _entry_label(table: str, data: dict, index: dict[str, dict[str, dict]]) -> str:
    if table == "product_components":
        product = index.get("commercial_products", {}).get(data.get("product_id", ""), {})
        material = index.get("materials", {}).get(data.get("material_id", ""), {})
        product_label = product.get("name") or data.get("product_id") or ""
        material_label = material.get("name") or data.get("material_id") or ""
        return f"{product_label} / {material_label}".strip(" /") or data.get("id", "")
    col = _NAME_COL.get(table)
    return (data.get(col) if col else None) or data.get("id", "")


def _component_rows(index: dict[str, dict[str, dict]], product_id: str) -> list[dict]:
    components = [
        row for row in index.get("product_components", {}).values()
        if row.get("product_id") == product_id
    ]
    return sorted(components, key=lambda row: row.get("id", ""))


def _fmt_number(value) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value or "")


class MergeTab(QWidget):
    def __init__(self, ref_path: Path):
        super().__init__()
        self.ref_path = ref_path
        self._sources: list[dict] = []
        self._payloads: dict[str, dict] = {}
        self._source_indexes: dict[str, dict[str, dict[str, dict]]] = {}
        self._ref_index: dict[str, dict[str, dict]] = {}
        self._entries: list[dict] = []   # analysed entries
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # Sélection des fichiers de contribution
        src_bar = QHBoxLayout()
        src_bar.addWidget(QLabel("Fichiers :"))
        self.src_label = QLabel("(aucun fichier sélectionné)")
        self.src_label.setStyleSheet("color: #888;")
        src_bar.addWidget(self.src_label, 1)

        buttons = [
            ("Tout…", None, "tout"),
            ("Facteurs…", ["emission_factors"], "facteurs"),
            ("Matériaux…", ["materials"], "matériaux"),
            ("Consommables…", ["commercial_products"], "consommables"),
            ("Composants…", ["product_components"], "composants"),
            ("Transport…", ["transport_factors"], "transport"),
            ("Sources…", ["sources"], "sources"),
            ("Contributeurs…", ["contributors"], "contributeurs"),
        ]
        for label, tables, scope in buttons:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, t=tables, s=scope: self._open_contribution(t, s))
            src_bar.addWidget(btn)

        btn_clear = QPushButton("Vider")
        btn_clear.clicked.connect(self._clear_sources)
        src_bar.addWidget(btn_clear)

        self.btn_analyze = QPushButton("Analyser")
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.clicked.connect(self._analyze)
        src_bar.addWidget(self.btn_analyze)
        root.addLayout(src_bar)

        # Légende
        legend = QHBoxLayout()
        for label, color in _SEV_COLOR.items():
            dot = QLabel(f"  ■ {label}  ")
            dot.setStyleSheet(f"background: {color.name()}; border-radius: 3px; padding: 2px 6px;")
            legend.addWidget(dot)
        legend.addStretch()
        root.addLayout(legend)

        # Splitter : tableau en haut, diff en bas
        splitter = QSplitter(Qt.Orientation.Vertical)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._show_diff)
        splitter.addWidget(self.table)

        self.diff_view = QTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setMaximumHeight(180)
        self.diff_view.setFont(QFont("Courier", 10))
        self.diff_view.setPlaceholderText("Sélectionnez une ligne pour voir le détail…")
        splitter.addWidget(self.diff_view)
        splitter.setSizes([420, 160])
        root.addWidget(splitter)

        # Sélection
        sel_bar = QHBoxLayout()
        btn_all  = QPushButton("Tout cocher")
        btn_none = QPushButton("Tout décocher")
        btn_new  = QPushButton("Cocher nouveaux")
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none.clicked.connect(lambda: self._set_all(False))
        btn_new.clicked.connect(self._check_new_only)
        sel_bar.addWidget(btn_all)
        sel_bar.addWidget(btn_none)
        sel_bar.addWidget(btn_new)
        sel_bar.addStretch()
        self.sel_count = QLabel("0 sélectionné(e)s")
        sel_bar.addWidget(self.sel_count)
        root.addLayout(sel_bar)

        # Action
        act_bar = QHBoxLayout()
        self.btn_import = QPushButton("Importer la sélection dans la base de référence")
        self.btn_import.setEnabled(False)
        self.btn_import.setStyleSheet(
            "QPushButton { background:#1565c0; color:white; font-weight:bold; padding:6px 14px; }"
            "QPushButton:hover { background:#1976d2; }"
            "QPushButton:disabled { background:#aaa; }"
        )
        self.btn_import.clicked.connect(self._import_selected)
        act_bar.addWidget(self.btn_import)
        act_bar.addStretch()
        root.addLayout(act_bar)

    # ------------------------------------------------------------------

    def reload(self, ref_path: Path) -> None:
        self.ref_path = ref_path

    def _open_contribution(self, tables: list[str] | None, scope: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, f"Sélectionner le fichier {scope}",
            str(ROOT),
            "SQLite / JSON (*.sqlite *.db *.json);;Tous (*)",
        )
        if not path:
            return
        source_key = f"{len(self._sources)}:{Path(path)}:{scope}"
        self._sources.append({
            "key": source_key,
            "path": Path(path),
            "tables": tables,
            "scope": scope,
        })
        self._refresh_source_label()
        self.btn_analyze.setEnabled(True)

    def _clear_sources(self) -> None:
        self._sources = []
        self._payloads = {}
        self._source_indexes = {}
        self._entries = []
        self.table.clearContents()
        self.table.setRowCount(0)
        self.diff_view.clear()
        self._refresh_source_label()
        self.btn_analyze.setEnabled(False)
        self.btn_import.setEnabled(False)

    def _refresh_source_label(self) -> None:
        if not self._sources:
            self.src_label.setText("(aucun fichier sélectionné)")
            self.src_label.setStyleSheet("color: #888;")
            return
        labels = [f"{src['path'].name} [{src['scope']}]" for src in self._sources]
        if len(labels) > 3:
            labels = labels[:3] + [f"+{len(self._sources) - 3} autre(s)"]
        self.src_label.setText(" ; ".join(labels))
        self.src_label.setStyleSheet("color: #333;")

    def _analyze(self) -> None:
        if not self._sources:
            return
        self._entries = []
        self._payloads = {}
        self._source_indexes = {}
        self._ref_index = _sqlite_index(self.ref_path)
        try:
            for source in self._sources:
                if source["path"].suffix == ".json":
                    self._entries.extend(self._analyze_json(source))
                else:
                    self._entries.extend(self._analyze_sqlite(source))
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'analyse", str(e))
            return
        self._populate_table()

    def _analyze_json(self, source: dict) -> list[dict]:
        payload = load_contribution_payload(source["path"])
        source_key = source["key"]
        self._payloads[source_key] = payload
        self._source_indexes[source_key] = _payload_index(payload)
        results = []
        for entry in self._filtered_payload_entries(payload, source["tables"]):
            table = entry.get("table")
            data  = entry.get("data", {})
            if table not in _MERGE_TABLES:
                continue
            eid = data.get("id", "")
            label = _entry_label(table, data, self._source_indexes[source_key])
            existing = self._ref_index.get(table, {}).get(eid)

            if existing is None:
                kind = "NOUVEAU"
                diffs = []
            else:
                diffs = diff_rows(dict(existing), data)
                kind = "CONFLIT" if diffs else None
            if kind:
                results.append({"kind": kind, "table": table, "id": eid,
                                 "label": label, "data": data,
                                 "existing": existing or {},
                                 "diffs": diffs,
                                 "source_key": source_key,
                                 "source_label": f"{source['path'].name} [{source['scope']}]",
                                 "source_path": str(source["path"])})
        # Chercher doublons de nom dans la référence
        self._flag_name_duplicates(results)
        return results

    def _analyze_sqlite(self, source: dict) -> list[dict]:
        source_key = source["key"]
        self._source_indexes[source_key] = _sqlite_index(source["path"])
        results = []
        for table, rows in self._filtered_sqlite_rows(source).items():
            try:
                ref_rows = self._ref_index.get(table, {})
            except Exception:
                continue
            for eid, cont_data in rows.items():
                label = _entry_label(table, cont_data, self._source_indexes[source_key])
                if eid not in ref_rows:
                    kind = "NOUVEAU"
                    diffs = []
                else:
                    diffs = diff_rows(ref_rows[eid], cont_data)
                    kind = "CONFLIT" if diffs else None
                if kind:
                    results.append({"kind": kind, "table": table, "id": eid,
                                     "label": label, "data": cont_data,
                                     "existing": ref_rows.get(eid, {}),
                                     "diffs": diffs,
                                     "source_key": source_key,
                                     "source_label": f"{source['path'].name} [{source['scope']}]",
                                     "source_path": str(source["path"])})
        self._flag_name_duplicates(results)
        return results

    def _filtered_payload_entries(
        self,
        payload: dict,
        tables: list[str] | None,
    ) -> list[dict]:
        entries_by_key = {}
        for table in ("sources", "contributors"):
            for row in payload.get(table, []):
                if row.get("id"):
                    entries_by_key[(table, row["id"])] = {
                        "table": table,
                        "id": row["id"],
                        "data": row,
                    }
        for entry in payload.get("entries", []):
            table = entry.get("table")
            data = entry.get("data", {})
            if table in _MERGE_TABLES and data.get("id"):
                entries_by_key[(table, data["id"])] = entry
        rows = self._selected_rows_from_index(_payload_index(payload), tables)
        return [
            entries_by_key.get((table, row_id), {"table": table, "id": row_id, "data": data})
            for table in _MERGE_TABLES
            for row_id, data in rows.get(table, {}).items()
        ]

    def _filtered_sqlite_rows(self, source: dict) -> dict[str, dict[str, dict]]:
        index = self._source_indexes[source["key"]]
        return self._selected_rows_from_index(index, source["tables"])

    def _selected_rows_from_index(
        self,
        index: dict[str, dict[str, dict]],
        tables: list[str] | None,
    ) -> dict[str, dict[str, dict]]:
        selected_tables = tables or _MERGE_TABLES
        rows = {table: dict(index.get(table, {})) for table in selected_tables}
        if tables is None:
            return rows

        def add(table: str, row_id: str | None) -> bool:
            if not row_id:
                return False
            row = index.get(table, {}).get(row_id)
            if not row:
                return False
            table_rows = rows.setdefault(table, {})
            if row_id in table_rows:
                return False
            table_rows[row_id] = row
            return True

        changed = True
        while changed:
            changed = False
            for table, table_rows in list(rows.items()):
                for row_id, row in list(table_rows.items()):
                    changed |= add("sources", row.get("source_id"))
                    changed |= add("contributors", row.get("contributor_id"))
                    changed |= add("contributors", row.get("validated_by_id"))

                    if table == "sources":
                        changed |= add("contributors", row.get("contributor_id"))
                    elif table == "materials":
                        changed |= add("emission_factors", row.get("emission_factor_id"))
                    elif table == "commercial_products":
                        changed |= add("emission_factors", row.get("emission_factor_id"))
                        for comp in _component_rows(index, row_id):
                            changed |= add("product_components", comp.get("id"))
                    elif table == "product_components":
                        changed |= add("commercial_products", row.get("product_id"))
                        changed |= add("materials", row.get("material_id"))

        return rows

    def _flag_name_duplicates(self, results: list[dict]) -> None:
        """Marque DOUBLON les entrées nouvelles dont le nom existe déjà (ID différent)."""
        for entry in results:
            if entry["kind"] != "NOUVEAU":
                continue
            table    = entry["table"]
            name_col = _NAME_COL.get(table)
            if not name_col:
                continue
            label = entry["data"].get(name_col, "")
            if not label:
                continue
            match = next(
                (
                    row for row in self._ref_index.get(table, {}).values()
                    if str(row.get(name_col) or "").strip().lower() == str(label).strip().lower()
                ),
                None,
            )
            if match and match.get("id") != entry["id"]:
                entry["kind"] = "DOUBLON"
                entry["diffs"] = [f"  ID existant : {match.get('id')}"]

    def _lookup(self, entry: dict, table: str, row_id: str | None) -> dict:
        if not row_id:
            return {}
        source_index = self._source_indexes.get(entry.get("source_key", ""), {})
        return (
            source_index.get(table, {}).get(row_id)
            or self._ref_index.get(table, {}).get(row_id)
            or {}
        )

    def _factor_summary(self, entry: dict, factor_id: str | None) -> tuple[str, str]:
        factor = self._lookup(entry, "emission_factors", factor_id)
        if not factor:
            return ("Facteur manquant" if factor_id else "", "")
        name = factor.get("name") or factor_id or ""
        co2 = factor.get("co2_factor")
        unit = factor.get("co2_unit") or "kgCO2e/kg"
        co2_text = "" if co2 is None else f"{_fmt_number(co2)} {unit}"
        return name, co2_text

    def _source_title(self, entry: dict, data: dict) -> str:
        source_id = data.get("source_id")
        source = self._lookup(entry, "sources", source_id)
        return source.get("title") or source_id or ""

    def _component_text(self, entry: dict, component: dict) -> str:
        material = self._lookup(entry, "materials", component.get("material_id"))
        material_name = material.get("name") or component.get("material_id") or "matériau manquant"
        parts = [str(component.get("component_type") or "composant"), material_name]
        if component.get("mass_g") is not None:
            parts.append(f"{_fmt_number(component['mass_g'])} g")
        divisor = component.get("units_divisor") or 1
        if divisor and divisor != 1:
            parts.append(f"/ {_fmt_number(divisor)}")
        factor_name, co2_text = self._factor_summary(entry, material.get("emission_factor_id"))
        if factor_name:
            parts.append(f"facteur: {factor_name}")
        if co2_text:
            parts.append(co2_text)
        return " ; ".join(parts)

    def _product_components_summary(self, entry: dict, product_id: str) -> tuple[str, str]:
        index = self._source_indexes.get(entry.get("source_key", ""), {})
        components = _component_rows(index, product_id)
        if not components:
            components = _component_rows(self._ref_index, product_id)
        if not components:
            return "Aucun composant lu", ""
        complete = [comp for comp in components if comp.get("mass_g") is not None]
        summary = f"{len(components)} composant(s)"
        if complete:
            summary += f", {len(complete)} avec masse"
        details = "\n".join(f"  - {self._component_text(entry, comp)}" for comp in components)
        return summary, details

    def _display_values(self, entry: dict) -> list[str]:
        table = entry["table"]
        data = entry["data"]
        nacres = data.get("code_nacres") or ""
        type_value = ""
        factor_text = ""
        co2_text = ""
        source_text = self._source_title(entry, data)
        packaging_count = ""

        if table == "emission_factors":
            type_value = data.get("factor_type") or ""
            factor_text = data.get("name") or ""
            co2 = data.get("co2_factor")
            unit = data.get("co2_unit") or "kgCO2e/kg"
            co2_text = "" if co2 is None else f"{_fmt_number(co2)} {unit}"
        elif table == "materials":
            type_value = "material"
            factor_text, co2_text = self._factor_summary(entry, data.get("emission_factor_id"))
        elif table == "commercial_products":
            type_value = data.get("product_type") or ""
            packaging_count = _fmt_number(data.get("units_per_sold_packaging"))
            if type_value == "liquid":
                factor_text, co2_text = self._factor_summary(entry, data.get("emission_factor_id"))
            else:
                factor_text, _ = self._product_components_summary(entry, data.get("id", ""))
        elif table == "product_components":
            product = self._lookup(entry, "commercial_products", data.get("product_id"))
            nacres = product.get("code_nacres") or ""
            type_value = product.get("product_type") or ""
            packaging_count = _fmt_number(product.get("units_per_sold_packaging"))
            factor_text = self._component_text(entry, data)
        elif table == "transport_factors":
            type_value = data.get("mode") or ""
            co2 = data.get("factor_kgco2e_per_kg")
            factor_text = data.get("origin") or ""
            co2_text = "" if co2 is None else f"{_fmt_number(co2)} kgCO2e/kg"
        elif table == "sources":
            type_value = data.get("source_type") or ""
        elif table == "contributors":
            type_value = data.get("team") or data.get("lab") or ""

        return [
            entry["kind"],
            entry.get("source_label", ""),
            _TABLE_LABEL.get(table, table),
            nacres,
            type_value,
            entry["label"],
            packaging_count,
            factor_text,
            co2_text,
            source_text,
            data.get("status", ""),
        ]

    def _populate_table(self) -> None:
        headers = [
            "",
            "Type",
            "Fichier",
            "Table",
            "NACRES",
            "Solide / liquide",
            "Nom / Origine",
            "Nbr cond.",
            "FE / comp.",
            "CO₂",
            "Source",
            "Statut source",
        ]
        try:
            self.table.itemChanged.disconnect(self._on_check_changed)
        except (RuntimeError, TypeError):
            pass
        self.table.blockSignals(True)
        self.table.clearContents()
        self.table.setRowCount(len(self._entries))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setColumnWidth(0, 28)
        for col, width in ((7, 80), (8, 150)):
            self.table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.Interactive
            )
            self.table.setColumnWidth(col, width)

        for r, entry in enumerate(self._entries):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            chk.setData(Qt.ItemDataRole.UserRole, r)
            color = _SEV_COLOR.get(entry["kind"], QColor(255, 255, 255))
            chk.setBackground(color)
            self.table.setItem(r, 0, chk)

            for c, val in enumerate(self._display_values(entry)):
                item = QTableWidgetItem(str(val or ""))
                item.setBackground(color)
                self.table.setItem(r, c + 1, item)

        self.table.blockSignals(False)
        self.table.itemChanged.connect(self._on_check_changed)
        self._update_sel_count()
        n = len(self._entries)
        n_new  = sum(1 for e in self._entries if e["kind"] == "NOUVEAU")
        n_conf = sum(1 for e in self._entries if e["kind"] == "CONFLIT")
        n_dup  = sum(1 for e in self._entries if e["kind"] == "DOUBLON")
        self.diff_view.setPlaceholderText(
            f"Analyse : {n} différences  |  {n_new} nouveaux  |  {n_conf} conflits  |  {n_dup} doublons"
        )

    def _show_diff(self) -> None:
        rows = self.table.selectedItems()
        if not rows:
            return
        r = self.table.currentRow()
        if r >= len(self._entries):
            return
        entry = self._entries[r]
        table = entry["table"]
        data = entry["data"]
        values = self._display_values(entry)
        lines = [
            f"[{entry['kind']}]  {_TABLE_LABEL.get(table, table)}  -  {entry['label']}",
            f"Fichier : {entry.get('source_label', '')}",
            f"ID : {entry.get('id', '')}",
            f"NACRES : {values[3]}",
            f"Type : {values[4]}",
            f"Nbr conditionnement : {values[6]}",
            f"FE / composants : {values[7]}",
            f"CO2 : {values[8]}",
            f"Source : {values[9]}",
        ]
        if table == "commercial_products" and data.get("product_type") != "liquid":
            _, details = self._product_components_summary(entry, data.get("id", ""))
            if details:
                lines.extend(["", "Composants lus :", details])
        elif table == "product_components":
            lines.extend(["", "Composant lu :", f"  - {self._component_text(entry, data)}"])
        if entry["diffs"]:
            lines.append("\nDifférences :")
            lines.extend(entry["diffs"])
        elif entry["kind"] == "NOUVEAU":
            lines.append("\nEntrée absente de la base de référence.")
        self.diff_view.setPlainText("\n".join(lines))

    def _on_check_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._update_sel_count()

    def _update_sel_count(self) -> None:
        n = sum(
            1 for r in range(self.table.rowCount())
            if self.table.item(r, 0) and
               self.table.item(r, 0).checkState() == Qt.CheckState.Checked
        )
        self.sel_count.setText(f"{n} sélectionné(e)s")
        self.btn_import.setEnabled(n > 0)

    def _set_all(self, state: bool) -> None:
        self.table.blockSignals(True)
        cs = Qt.CheckState.Checked if state else Qt.CheckState.Unchecked
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0):
                self.table.item(r, 0).setCheckState(cs)
        self.table.blockSignals(False)
        self._update_sel_count()

    def _check_new_only(self) -> None:
        self.table.blockSignals(True)
        for r, entry in enumerate(self._entries):
            item = self.table.item(r, 0)
            if item:
                cs = Qt.CheckState.Checked if entry["kind"] == "NOUVEAU" else Qt.CheckState.Unchecked
                item.setCheckState(cs)
        self.table.blockSignals(False)
        self._update_sel_count()

    def _source_by_key(self, source_key: str) -> dict:
        return next((src for src in self._sources if src["key"] == source_key), {})

    def _dependency_entry(self, table: str, row_id: str, source_key: str) -> dict | None:
        if not row_id or row_id in self._ref_index.get(table, {}):
            return None
        data = self._source_indexes.get(source_key, {}).get(table, {}).get(row_id)
        if not data:
            return None
        source = self._source_by_key(source_key)
        return {
            "kind": "DEPENDANCE",
            "table": table,
            "id": row_id,
            "label": _entry_label(table, data, self._source_indexes.get(source_key, {})),
            "data": data,
            "existing": {},
            "diffs": [],
            "source_key": source_key,
            "source_label": f"{source.get('path', Path('')).name} [{source.get('scope', '')}]",
            "source_path": str(source.get("path", "")),
        }

    def _expand_entries_for_import(self, entries: list[dict]) -> tuple[list[dict], int]:
        expanded = list(entries)
        seen = {(entry["table"], entry["id"]) for entry in expanded}
        auto_count = 0

        def add_missing(table: str, row_id: str | None, source_key: str) -> None:
            nonlocal auto_count
            if not row_id:
                return
            key = (table, row_id)
            if key in seen:
                return
            dep = self._dependency_entry(table, row_id, source_key)
            if not dep:
                return
            expanded.append(dep)
            seen.add(key)
            auto_count += 1

        i = 0
        while i < len(expanded):
            entry = expanded[i]
            table = entry["table"]
            data = entry["data"]
            source_key = entry.get("source_key", "")

            add_missing("sources", data.get("source_id"), source_key)
            add_missing("contributors", data.get("contributor_id"), source_key)
            add_missing("contributors", data.get("validated_by_id"), source_key)

            if table == "sources":
                add_missing("contributors", data.get("contributor_id"), source_key)
            elif table == "materials":
                add_missing("emission_factors", data.get("emission_factor_id"), source_key)
            elif table == "commercial_products":
                add_missing("emission_factors", data.get("emission_factor_id"), source_key)
                for comp in _component_rows(
                    self._source_indexes.get(source_key, {}),
                    data.get("id", ""),
                ):
                    add_missing("product_components", comp.get("id"), source_key)
            elif table == "product_components":
                add_missing("commercial_products", data.get("product_id"), source_key)
                add_missing("materials", data.get("material_id"), source_key)

            i += 1

        return expanded, auto_count

    def _import_selected(self) -> None:
        selected_idx = [
            self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)
            for r in range(self.table.rowCount())
            if self.table.item(r, 0) and
               self.table.item(r, 0).checkState() == Qt.CheckState.Checked
        ]
        if not selected_idx:
            return
        entries = [self._entries[i] for i in selected_idx]
        conflicts = [e for e in entries if e["kind"] == "CONFLIT"]
        msg = f"Importer {len(entries)} entrée(s) dans la base de référence ?"
        if conflicts:
            msg += f"\n\n⚠  {len(conflicts)} conflit(s) : la version de la contribution écrasera la référence."
        reply = QMessageBox.question(self, "Confirmer l'import", msg,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._ref_index = _sqlite_index(self.ref_path)
            entries, auto_dependencies = self._expand_entries_for_import(entries)
            conn = sqlite3.connect(self.ref_path)
            conn.execute("PRAGMA foreign_keys = ON")
            json_dependencies = 0
            for source_key in {entry.get("source_key", "") for entry in entries}:
                payload = self._payloads.get(source_key)
                if payload is not None:
                    json_dependencies += import_dependencies(
                        conn, payload, dry_run=False, logger=None
                    )
            stats = apply_contribution_entries(
                conn,
                entries,
                validate=False,
                dry_run=False,
                logger=None,
            )
            stats.dependencies = json_dependencies
            conn.commit()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'import", str(e))
            return
        QMessageBox.information(
            self,
            "Import terminé",
            (
                f"{stats.new} nouvelle(s), {stats.updated} mise(s) à jour, "
                f"{stats.skipped} inchangée(s).\n"
                f"{auto_dependencies} dépendance(s) auto sélectionnée(s), "
                f"{stats.dependencies} source(s)/contributeur(s) ajouté(s)."
            ),
        )
        self._analyze()


# ============================================================
# Onglet 3 — Qualité
# ============================================================

class QualityTab(QWidget):
    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = db_path
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        top = QHBoxLayout()
        self.btn_run = QPushButton("Lancer l'audit")
        self.btn_run.clicked.connect(self._run)
        top.addWidget(self.btn_run)
        self.summary_label = QLabel("")
        top.addWidget(self.summary_label)
        top.addStretch()
        root.addLayout(top)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table)

    def reload(self, db_path: Path) -> None:
        self.db_path = db_path
        self.table.clearContents()
        self.table.setRowCount(0)
        self.summary_label.setText("")

    def _run(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            issues = check_database(conn)
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))
            return

        n_err  = sum(1 for i in issues if i.severity == "ERROR")
        n_warn = sum(1 for i in issues if i.severity == "WARNING")
        n_info = sum(1 for i in issues if i.severity == "INFO")
        self.summary_label.setText(
            f"  {n_err} erreur(s)  |  {n_warn} avertissement(s)  |  {n_info} info(s)"
        )

        headers = ["Sévérité", "Table", "Règle", "Entrée", "Détail"]
        _colors = {"ERROR": QColor(255, 205, 210), "WARNING": QColor(255, 243, 178),
                   "INFO": QColor(232, 245, 233)}

        self.table.blockSignals(True)
        self.table.clearContents()
        visible = [i for i in issues if i.severity != "INFO"]
        self.table.setRowCount(len(visible))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        for r, issue in enumerate(visible):
            color = _colors.get(issue.severity, QColor(255, 255, 255))
            for c, val in enumerate([issue.severity, issue.table, issue.rule,
                                      issue.entry, issue.detail]):
                item = QTableWidgetItem(str(val or ""))
                item.setBackground(color)
                self.table.setItem(r, c, item)
        self.table.blockSignals(False)


# ============================================================
# Fenêtre principale
# ============================================================

class AdminWindow(QMainWindow):
    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = db_path
        self.setWindowTitle(f"LABeCO2 Admin — {db_path.name}")
        self.resize(1200, 750)
        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Barre base de données
        db_bar = QHBoxLayout()
        db_bar.addWidget(QLabel("Base de référence :"))
        self.db_label = QLabel(str(self.db_path))
        self.db_label.setStyleSheet("font-weight: bold;")
        db_bar.addWidget(self.db_label, 1)
        btn_change = QPushButton("Charger…")
        btn_change.setMaximumWidth(100)
        btn_change.clicked.connect(self._change_db)
        db_bar.addWidget(btn_change)
        root.addLayout(db_bar)

        # Onglets
        self.tabs = QTabWidget()
        self.tab_validate = ValidationTab(self.db_path)
        self.tab_merge    = MergeTab(self.db_path)
        self.tab_quality  = QualityTab(self.db_path)
        self.tabs.addTab(self.tab_validate, "✓  Validation")
        self.tabs.addTab(self.tab_merge,    "⇄  Fusion / Conflits")
        self.tabs.addTab(self.tab_quality,  "⚠  Qualité")
        root.addWidget(self.tabs)

    def _change_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner la base SQLite",
            str(ROOT / "private"),
            "SQLite (*.sqlite *.db);;Tous (*)",
        )
        if not path:
            return
        self.db_path = Path(path)
        self.db_label.setText(str(self.db_path))
        self.setWindowTitle(f"LABeCO2 Admin — {self.db_path.name}")
        self.tab_validate.reload(self.db_path)
        self.tab_merge.reload(self.db_path)
        self.tab_quality.reload(self.db_path)


# ============================================================
# Point d'entrée
# ============================================================

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="LABeCO2 — Outil d'administration")
    parser.add_argument("--db", default=str(ROOT / "private" / "labeco2.sqlite"))
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Base introuvable : {db_path}", file=sys.stderr)
        print("Initialisez-la depuis data/labeco2_reference.sqlite ou lancez l'application une première fois.", file=sys.stderr)
        sys.exit(1)

    app = QApplication.instance() or QApplication(sys.argv)
    win = AdminWindow(db_path)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
