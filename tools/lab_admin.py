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
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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
        self._edit_window = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._widget = ValidateWidget(db_path, show_close=False, parent=self)
        self._widget.edit_requested.connect(self._on_edit_requested)
        layout.addWidget(self._widget)

    def reload(self, db_path: Path) -> None:
        self.db_path = db_path
        self._widget.sqlite_path = db_path
        self._widget._load_table()

    def _on_edit_requested(self, table: str, row_id: str) -> None:
        import sqlite3
        from ui.data_mass_window import DataMassWindow

        factor_id = row_id
        if table == "materials":
            try:
                with sqlite3.connect(self.db_path) as conn:
                    r = conn.execute(
                        "SELECT emission_factor_id FROM materials WHERE id = ?", (row_id,)
                    ).fetchone()
                    if r and r[0]:
                        factor_id = r[0]
            except Exception:
                pass

        win = DataMassWindow(
            parent=self,
            base_path=str(ROOT),
            user_path=str(ROOT),
            mode_filter="factor",
            sqlite_path=self.db_path,
        )
        win.prefill_factor_from_sqlite(factor_id)
        win.data_added.connect(self._widget._load_table)
        win.show()
        self._edit_window = win


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
        note_text = data.get("note") or ""

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
            note_text,
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
            "Lien / Note",
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
            f"Lien / Note : {values[10]}",
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
# Suggestion NACRES par mots-clés
# ============================================================

# Règles ordonnées : la première qui matche l'emporte.
# Tuple (keywords_lower, nacres_code, label_raison)
_NACRES_RULES: list[tuple[list[str], str, str]] = [
    # Enzymes (avant "ase" générique)
    (["cellulase", "macerozyme", "pectolyase", "zymolyase", "protease",
      "lipase", "amylase", "nuclease", "lysozyme", "pectinase"],
     "NA52", "enzyme"),

    # Antibiotiques / antimicrobiens / antifongiques
    (["mycin", "cillin", "cycline", "cyclin", "oxacin", "floxacin",
      "amphotericin", "cefotaxime", "cephalexin",
      "trimethoprim", "sulphamethoxazole", "chloramphenicol",
      "phleomycin", "zeocin", "bleomycin", "metronidazole",
      "miconazole", "griseofulvin", "cetrimide", "cetrimonium",
      "chlorhexidine", "chloroxylenol", "thimerosal",
      "rifamp", "colistin", "bacitracin",
      "acyclovir", "ribavirin", "cycloheximide", "validamycin",
      "doxorubicin", "fluoro uracil", "5-foa",
      "chlorsulfuron", "phosphinotricin", "paromomycin",
      "nalidixic", "g-418", "d-cycloserine", "carboxin",
      "mercaptopurine", "methotrexate"],
     "NA76", "antibiotique/antimicrobien"),

    # Milieux de culture / gélifiants / supports
    (["medium", "media", "broth", "murashige", "skoog", " ms ", "b5 ",
      "plant agar", "micro agar", "phyto agar", "daishin agar",
      "malt agar", "malt extract", "luria", "peptone", "yeast extract",
      "gelrite", "gelcarin", "carrageenan", "agarose", "low melting",
      "seaplaque", "vitamin mixture", "salt mixture", "soya peptone",
      "casein hydrolysate"],
     "NA71", "milieu de culture / gélifiant"),

    # Agar seul (nom court)
    (["agar"],
     "NA71", "gélifiant"),

    # Solvants non halogénés
    (["dimethylsulfoxide", "dmso", "ethanol", "methanol", "acetone",
      "isopropanol", "propanol", "glycerol", "glycerin"],
     "NA03", "solvant non halogéné"),

    # Acides (inorganiques/organiques concentrés)
    (["hydrochloric acid", "sulphuric acid", "nitric acid",
      "phosphoric acid", "perchloric acid", "acetic acid glacial"],
     "NA04", "acide"),

    # Bases
    (["sodium hydroxide", "potassium hydroxide", "naoh", "koh"],
     "NA05", "base"),

    # Sels inorganiques / minéraux
    (["chloride", "sulphate", "sulfate", "nitrate", "phosphate",
      "hydroxide", "carbonate", "citrate", "gluconate",
      "molybdate", "thiosulphate", "edta", "fenaedta", "ferrous",
      "cupric", "aluminium", "cobalt", "manganese", "magnesium",
      "ammonium", "silver nitrate", "zinc sulphate", "boric acid",
      "potassium iodide", "sodium alginate", "sodium dodecyl",
      "sds"],
     "NA21", "sel inorganique / minéral"),

    # Réactifs organiques : acides aminés, vitamines, hormones, tampons, sucres
    (["l-alanine", "l-arginine", "l-asparagine", "l-aspartic",
      "l-cysteine", "l-glutamine", "l-glutamic", "l-histidine",
      "l-isoleucine", "l-leucine", "l-lysine", "l-methionine",
      "l-ornithine", "l-phenylalanine", "l-proline", "l-serine",
      "l-threonine", "l-tryptophan", "l-tyrosine", "l-valine",
      "glycine", "amino acid",
      "thiamine", "pyridoxine", "nicotinic acid", "nicotinamide",
      "folic acid", "folinate", "biotin", "biotine", "choline",
      "cyanocobalamin", "pantothenate", "inositol", "riboflavin",
      "ascorbic acid", "p-aminobenzoic",
      "sucrose", "glucose", "fructose", "galactose", "mannose",
      "mannitol", "sorbitol", "ribose", "lactose", "maltose",
      "trehalose", "raffinose", "xylose",
      "kinetin", "zeatin", "benzylaminopurine", "6-bap", "bap",
      "indole-3-acetic", "iaa", "indole-3-butyric", "iba",
      "naphthalene acetic", "naa", "gibberellic", "gibberellin",
      "abscisic", "thidiazuron", "cppu", "meta-topoline",
      "picloram", "dicamba", "2,4-d", "2,4 d", "4-cpa",
      "paclobutrazol", "flurprimidol", "fluridon", "oryzaline",
      "colchicine", "epibrassinolide", "methyl jasmonate",
      "jasmonic acid", "salicylic acid",
      "hepes", "mes ", "mops", "tris", "pipes", "bes ", "bis-tris",
      "triethanolamine", "taurine", "spermidine",
      "citric acid", "malic acid", "acetylsalicylic",
      "polyethylene glycol", "peg ", "peg4", "peg6",
      "dithioerythreitol", "dte", "gluthatione",
      "charcoal activated", "starch",
      "dextran sulphate", "adenine", "adenosine", "atp",
      "iptg", "x-gal", "x-phos", "x-glca", "blue-gal",
      "salmon gal", "mug ", "ntb", "bcip",
      "guanidine", "hydroxyquinoline", "fluoroorotic",
      # herbicides / régulateurs non listés ailleurs
      "atrazine", "bromoxynil", "trifluralin", "amiprophos",
      "maleic hydrazide", "dicamba",
      # hormones avec graphie alternative
      "abscisic", "absisic", "naphtalene acetic", "naphtoxyacetic",
      "triiodobenzoic", "trichlorophenoxyacetic", "chlorophenoxyacetic",
      "riboside",
      # tampons / détergents non listés
      "chaps", "bes", "bis-tris",
      # substrats enzymatiques / indicateurs
      "luciferin", "mtt", "esculin", "nitrophenyl",
      "urea", "thimerosal"],
     "NA25", "réactif organique"),
]

_COLOR_SUGGESTION = QColor(200, 220, 255)   # bleu clair : suggestion IA


def suggest_nacres(name: str) -> tuple[str, str]:
    """Retourne (nacres_code, raison) depuis le nom du produit, ou ('', '') si inconnu."""
    name_l = name.lower()
    for keywords, code, reason in _NACRES_RULES:
        if any(kw in name_l for kw in keywords):
            return code, reason
    return "", ""


# ============================================================
# Labels officiels NACRES (64 codes présents dans la base)
# ============================================================

_NACRES_LABELS: dict[str, str] = {
    "AA01": "PAINS, PATISSERIES, VIENNOISERIES CONGELES",
    "AA23": "CONSERVES ET EPICERIE",
    "AA41": "CONSOMMABLES POUR LA RESTAURATION",
    "AA42": "PETITES FOURNITURES POUR LA RESTAURATION",
    "AB01": "PETITES FOURNITURES ET PETITS EQUIPEMENTS DE BUREAU (HORS INFORMATIQUE)",
    "AC01": "PAPIERS BLANCS OU COLORES COURANTS POUR IMPRESSION-REPROGRAPHIE",
    "AC02": "PAPIERS CARTONNES POUR IMPRESSION-REPROGRAPHIE",
    "BB01": "PRODUITS ET PETITES FOURNITURES D'HYGIENE ET DE TOILETTE",
    "BB02": "PRODUITS ET PETITES FOURNITURES D'ENTRETIEN MENAGER",
    "BD21": "PETITES FOURNITURES ELECTRIQUES POUR L'EQUIPEMENT DES BATIMENTS ET INFRASTR.",
    "FA01": "FOURNITURES D'EMBALLAGE ET DE TRANSPORT DE MARCHANDISES ORDINAIRES",
    "HA01": "EPI : GANTS A USAGE UNIQUE",
    "HA02": "EPI : AUTRES EPI JETABLES (BLOUSES, SURCHAUSSES, CHARLOTTES, MASQUES...)",
    "HA03": "EPI : BLOUSES ET AUTRES VETEMENTS DE LABORATOIRE REUTILISABLES",
    "HA04": "EPI : VETEMENTS DE TRAVAIL ET DE PROTECTION COURANTS (HORS LABORATOIRE)",
    "HA05": "EPI : ACCESSOIRES (LUNETTES, CASQUES, ETC...)",
    "HA11": "CONSOMMABLES POUR RECEPTION DES DECHETS (ABSORBANTS, RECIPIENTS...)",
    "IA24": "AUTRE MATERIEL INFORMATIQUE PERIPHERIQUE (ECRANS, CLAVIERS, SOURIS...)",
    "KE12": "MATERIELS CHIRUGICAUX ET DE TECHNIQUES OPERATOIRES ANIMALES",
    "KE13": "CONSOMMABLES D'ANESTHESIE ET DE TECHNIQUES OPERATOIRES ANIMALES",
    "MA45": "LAMPES POUR MICROSCOPES PHOTONIQUES ET DE FLUORESCENCE",
    "NA02": "SOLVANTS : ACETONE",
    "NA03": "SOLVANTS : ACETONITRILE",
    "NA04": "SOLVANTS : SOLVANTS CHLORES (DICHLOROMETHANE, CHLOROFORME...)",
    "NA05": "SOLVANTS : EAU ET ALCOOLS (METHANOL, ETHANOL, PROPAN-2-OL...)",
    "NA06": "SOLVANTS : HYDROCARBURES (PENTANE, HEXANE, HEPTANE...)",
    "NA07": "SOLVANTS : AUTRES SOLVANTS (ETHERS...)",
    "NA21": "PRODUITS CHIMIQUES COURANTS (ACIDES, BASES, SELS...)",
    "NA25": "PRODUITS BIOCHIMIQUES COURANTS (TAMPONS, BSA, etc.)",
    "NA26": "BIOLOGIE : PEPTIDES ET ACIDES AMINES",
    "NA28": "BIOLOGIE : PRODUITS CHIMIQUES A USAGE BIOCHIMIQUE OU BIOLOGIQUE",
    "NA31": "REACTIFS ET KITS POUR LE MARQUAGE ET LA DETECTION DES ACIDES NUCLEIQUES",
    "NA46": "ANTICORPS SECONDAIRES",
    "NA52": "KITS ET REACTIFS POUR L'ISOLEMENT ET LA PURIFICATION DES ACIDES NUCLEIQUES",
    "NA53": "ENZYMES DE RESTRICTION",
    "NA54": "ENZYMES DE MODIFICATION ET DE CLONAGE (Nucleases, Kinases, Phosphatases)",
    "NA55": "ENZYMES ET KITS DE SYNTHESE DES ACIDES NUCLEIQUES (PCR...)",
    "NA56": "KITS ET REACTIFS POUR L'ISOLEMENT ET LA PURIFICATION DES PROTEINES",
    "NA71": "SERUMS ET AUTRES MILIEUX POUR CULTURE DE CELLULES ANIMALES",
    "NA73": "MILIEUX POUR CULTURE DE PETITS ORGANISMES VIVANTS",
    "NA76": "ANTIBIOTIQUES POUR CULTURE CELLULAIRE",
    "NA78": "ENZYMES POUR CULTURE CELLULAIRE",
    "NB01": "MICROPIPETTES MONO-CANAL, MULTI-CANAUX ET ACCESSOIRES",
    "NB02": "POINTES (CONES) POUR MICROPIPETTES MONO-CANAL ET MULTI-CANAUX",
    "NB03": "SERINGUES EN PLASTIQUE ET AIGUILLES",
    "NB04": "PIPETTES A USAGE UNIQUE",
    "NB05": "PIPETTES REUTILISABLES",
    "NB11": "MICROTUBES, CRYOTUBES, TUBES A USAGE UNIQUE",
    "NB12": "PORTOIRS ET BOITES DE STOCKAGE POUR MICROTUBES",
    "NB13": "CULTURE CELLULAIRE EUCARYOTE : CONSOMMABLES EN PLASTIQUE SPECIFIQUES",
    "NB14": "BACTERIOLOGIE : CONSOMMABLES EN PLASTIQUE SPECIFIQUES",
    "NB15": "MICROPLAQUES (PCR, HTS, ELISA...) HORS CULTURE CELLULAIRE ET FILTRATION",
    "NB16": "LAMES ET LAMELLES EN VERRE ET PLASTIQUE",
    "NB17": "AUTRES CONSOMMABLES EN PLASTIQUE ET EN VERRE HORS CULTURE CELL. ET BACTERIO",
    "NB22": "ELECTROPHORESE SUR GEL : CONSOMMABLES NON DEDIES AUX INSTRUMENTS",
    "NB23": "MEMBRANES ET KITS POUR LE TRANSFERT D'ACIDES NUCLEIQUES ET DES PROTEINES (BLOT)",
    "NB24": "CONSOMMABLES POUR FILTRATION ET DIALYSE",
    "NB32": "HUILE A IMMERSION POUR MICROSCOPIE",
    "NB34": "PRODUITS DE LAVAGE, DESINFECTION, STERILISATION",
    "NB35": "AUTRES CONSOMMABLES DE LABO HORS PLASTIQUE ET VERRE",
    "NB43": "VAISSELLE DE LABORATOIRE REUTILISABLE EN VERRE, PLASTIQUE, PORCELAINE",
    "NB51": "PETIT MATERIEL DE PAILLASSE NON ELECTRIQUE COURANT",
    "NE02": "BIOLOGIE : SERVICES DE SEQUENCAGE HAUT DEBIT ET SERVICES CONNEXES",
    "TB12": "ENERGIE : PILES A L'UNITE ET ASSEMBLAGE DE PILES CLASSIQUES ET SPECIALES",
}

_NACRES_COMBO_ITEMS: list[str] = [""] + [
    f"{code} — {label}" for code, label in sorted(_NACRES_LABELS.items())
]


# ============================================================
# Onglet 4 — Catalogue fournisseurs (assignation NACRES)
# ============================================================

_COL_CHK     = 0   # checkbox (cocher pour sélectionner)
_COL_ID      = 1   # hidden product id
_COL_SUPPL   = 2
_COL_CODE    = 3   # code fournisseur (ex: A0602.0100 Duchefa, 08-212 IJM)
_COL_NAME    = 4
_COL_BRAND   = 5
_COL_CONDT   = 6
_COL_PRICE   = 7
_COL_TYPE    = 8
_COL_NACRES  = 9   # QComboBox pour les pending, read-only sinon
_COL_STATUS  = 10

_CATALOGUE_HEADERS = [
    "", "id", "Fournisseur", "Code catalogue", "Désignation", "Marque",
    "Conditionnement", "Prix HT (€)", "Type", "Code NACRES", "Statut",
]

_COLOR_PENDING    = QColor(255, 243, 180)   # jaune : en attente de validation
_COLOR_HAS_NACRES = QColor(210, 240, 210)   # vert  : NACRES confirmé
_COLOR_VALIDATED  = QColor(220, 235, 255)   # bleu clair : déjà validé


class CatalogueTab(QWidget):
    """Onglet d'assignation des codes NACRES aux produits importés (status=pending)."""

    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = db_path
        self._pending_changes: dict[str, str] = {}   # product_id → new nacres
        self._build_ui()
        self._load()

    def reload(self, db_path: Path) -> None:
        self.db_path = db_path
        self._pending_changes = {}
        self._load()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # Barre de filtre
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Fournisseur :"))
        self.supplier_combo = QComboBox()
        self.supplier_combo.addItem("Tous", "")
        self.supplier_combo.currentIndexChanged.connect(self._apply_filter)
        filter_bar.addWidget(self.supplier_combo)

        filter_bar.addWidget(QLabel("  Afficher :"))
        self.show_combo = QComboBox()
        self.show_combo.addItem("En attente (pending)", "pending")
        self.show_combo.addItem("Sans NACRES seulement", "missing")
        self.show_combo.addItem("Tous (IJM + Duchefa + ...)", "all")
        self.show_combo.currentIndexChanged.connect(self._apply_filter)
        filter_bar.addWidget(self.show_combo)

        filter_bar.addSpacing(12)
        filter_bar.addWidget(QLabel("Recherche :"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filtrer…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(200)
        self.search_edit.textChanged.connect(self._apply_filter)
        filter_bar.addWidget(self.search_edit)

        filter_bar.addStretch()
        self.count_label = QLabel("")
        filter_bar.addWidget(self.count_label)

        btn_reload = QPushButton("↺  Recharger")
        btn_reload.clicked.connect(self._load)
        filter_bar.addWidget(btn_reload)
        root.addLayout(filter_bar)

        # Légende
        legend = QHBoxLayout()
        for text, color in [
            ("En attente (sans NACRES)", _COLOR_PENDING),
            ("Suggestion auto", _COLOR_SUGGESTION),
            ("NACRES assigné", _COLOR_HAS_NACRES),
            ("Validé", _COLOR_VALIDATED),
        ]:
            lbl = QLabel(f"  ■ {text}  ")
            lbl.setStyleSheet(
                f"background:{color.name()}; color:black; border-radius:3px; padding:2px 6px;"
            )
            legend.addWidget(lbl)
        legend.addStretch()
        root.addLayout(legend)

        # Tableau
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setColumnCount(len(_CATALOGUE_HEADERS))
        self.table.setHorizontalHeaderLabels(_CATALOGUE_HEADERS)
        self.table.hideColumn(_COL_ID)
        self.table.setColumnWidth(_COL_CHK, 28)
        self.table.horizontalHeader().setSectionResizeMode(
            _COL_CHK, QHeaderView.ResizeMode.Fixed
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            _COL_CHK, QHeaderView.ResizeMode.Fixed
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self.table)

        # Actions
        act_bar = QHBoxLayout()
        self.unsaved_label = QLabel("")
        self.unsaved_label.setStyleSheet("color: #e65100; font-weight: bold;")
        act_bar.addWidget(self.unsaved_label)

        btn_check_all  = QPushButton("Tout cocher")
        btn_check_none = QPushButton("Tout décocher")
        btn_check_all.setMaximumWidth(110)
        btn_check_none.setMaximumWidth(110)
        btn_check_all.clicked.connect(lambda: self._set_all_checks(True))
        btn_check_none.clicked.connect(lambda: self._set_all_checks(False))
        act_bar.addWidget(btn_check_all)
        act_bar.addWidget(btn_check_none)
        act_bar.addStretch()

        self.btn_save = QPushButton("Sauvegarder les NACRES")
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet(
            "QPushButton{background:#1565c0;color:white;font-weight:bold;padding:6px 16px;}"
            "QPushButton:hover{background:#1976d2;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self.btn_save.clicked.connect(self._save)
        act_bar.addWidget(self.btn_save)

        self.btn_suggest = QPushButton("Suggérer NACRES automatiquement")
        self.btn_suggest.setToolTip(
            "Remplit les codes NACRES manquants par règles sur le nom du produit.\n"
            "Les suggestions apparaissent en bleu — à vérifier avant de sauvegarder."
        )
        self.btn_suggest.setStyleSheet(
            "QPushButton{background:#6a1b9a;color:white;font-weight:bold;padding:6px 16px;}"
            "QPushButton:hover{background:#7b1fa2;}"
        )
        self.btn_suggest.clicked.connect(self._auto_suggest)
        act_bar.addWidget(self.btn_suggest)

        self.btn_promote = QPushButton("Passer en draft (validation)")
        self.btn_promote.setToolTip(
            "Les produits avec un code NACRES passent en statut 'draft'\n"
            "et apparaissent dans l'onglet Validation pour être validés."
        )
        self.btn_promote.setStyleSheet(
            "QPushButton{background:#2e7d32;color:white;font-weight:bold;padding:6px 16px;}"
            "QPushButton:hover{background:#388e3c;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self.btn_promote.clicked.connect(self._promote_to_draft)
        act_bar.addWidget(self.btn_promote)
        root.addLayout(act_bar)

    # ------------------------------------------------------------------
    # Chargement
    # ------------------------------------------------------------------

    def _load(self) -> None:
        self._pending_changes = {}
        self._update_unsaved_label()

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row

            rows = conn.execute("""
                SELECT
                    cp.id,
                    COALESCE(sc.supplier, ijm.source_catalogue, 'Inconnu') AS supplier,
                    COALESCE(sc.code_fournisseur, ijm.code_ijm, cp.reference) AS code_catalogue,
                    cp.name,
                    cp.brand,
                    COALESCE(sc.conditionnement, ijm.conditionnement, cp.sold_packaging_label) AS conditionnement,
                    COALESCE(sc.price_ht, ijm.price_ht, cp.price_sold_packaging) AS price_ht,
                    cp.product_type,
                    COALESCE(cp.code_nacres, '') AS code_nacres,
                    cp.status
                FROM commercial_products cp
                LEFT JOIN supplier_catalogue sc  ON sc.id  = cp.supplier_catalogue_id
                LEFT JOIN catalogue_ijm      ijm ON ijm.id = cp.ijm_catalogue_id
                WHERE cp.status NOT IN ('deprecated')
                  AND (cp.supplier_catalogue_id IS NOT NULL OR cp.ijm_catalogue_id IS NOT NULL)
                ORDER BY supplier, cp.name
            """).fetchall()

            suppliers = sorted({r["supplier"] for r in rows if r["supplier"]})
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger les données : {e}")
            return

        # Mettre à jour le combo fournisseurs
        self.supplier_combo.blockSignals(True)
        current_supplier = self.supplier_combo.currentData()
        self.supplier_combo.clear()
        self.supplier_combo.addItem("Tous", "")
        for s in suppliers:
            self.supplier_combo.addItem(s, s)
        idx = self.supplier_combo.findData(current_supplier)
        if idx >= 0:
            self.supplier_combo.setCurrentIndex(idx)
        self.supplier_combo.blockSignals(False)

        # Remplir le tableau
        self.table.blockSignals(True)
        self.table.clearContents()
        self.table.setRowCount(len(rows))

        for r, row in enumerate(rows):
            nacres = row["code_nacres"] or ""
            status = row["status"] or ""
            is_pending = (status == "pending")
            if status in ("validated", "draft") and nacres:
                color = _COLOR_VALIDATED
            elif nacres:
                color = _COLOR_HAS_NACRES
            else:
                color = _COLOR_PENDING

            def _item(text, editable=False, row_color=color):
                it = QTableWidgetItem(str(text) if text is not None else "")
                it.setForeground(QColor(0, 0, 0))
                it.setBackground(row_color)
                if not editable:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                return it

            # Checkbox (sélection pour promotion) — uniquement pour les pending
            chk = QTableWidgetItem()
            chk.setBackground(color)
            if is_pending:
                chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                chk.setCheckState(Qt.CheckState.Unchecked)
            else:
                chk.setFlags(Qt.ItemFlag.ItemIsEnabled)

            self.table.setItem(r, _COL_CHK,    chk)
            self.table.setItem(r, _COL_ID,     _item(row["id"]))
            self.table.setItem(r, _COL_SUPPL,  _item(row["supplier"]))
            self.table.setItem(r, _COL_CODE,   _item(row["code_catalogue"]))
            self.table.setItem(r, _COL_NAME,   _item(row["name"]))
            self.table.setItem(r, _COL_BRAND,  _item(row["brand"]))
            self.table.setItem(r, _COL_CONDT,  _item(row["conditionnement"]))
            price = row["price_ht"]
            self.table.setItem(r, _COL_PRICE,  _item(f"{price:.2f}" if price else ""))
            self.table.setItem(r, _COL_TYPE,   _item(row["product_type"]))
            # NACRES : item caché (pour le filtrage) + QComboBox pour les pending
            self.table.setItem(r, _COL_NACRES, _item(nacres))
            if is_pending:
                combo = self._make_nacres_combo(r, nacres, color)
                self.table.setCellWidget(r, _COL_NACRES, combo)
            self.table.setItem(r, _COL_STATUS, _item(status))

        self.table.blockSignals(False)
        self._apply_filter()

    def _apply_filter(self) -> None:
        supplier_filter = self.supplier_combo.currentData() or ""
        show_mode = self.show_combo.currentData()
        needle = self.search_edit.text().strip().lower()

        total = self.table.rowCount()
        visible = 0
        for r in range(total):
            supplier_item = self.table.item(r, _COL_SUPPL)
            nacres_item   = self.table.item(r, _COL_NACRES)
            if not supplier_item:
                self.table.setRowHidden(r, True)
                continue

            supplier_val = supplier_item.text()
            # Pour les pending, lire la valeur depuis l'item caché (maintenu par les handlers)
            nacres_val   = (nacres_item.text() if nacres_item else "").strip()
            status_item  = self.table.item(r, _COL_STATUS)
            status_val   = (status_item.text() if status_item else "").strip()

            if supplier_filter and supplier_val != supplier_filter:
                self.table.setRowHidden(r, True)
                continue
            if show_mode == "pending" and status_val != "pending":
                self.table.setRowHidden(r, True)
                continue
            if show_mode == "missing" and nacres_val:
                self.table.setRowHidden(r, True)
                continue
            if needle:
                match = any(
                    (item := self.table.item(r, c)) is not None
                    and needle in item.text().lower()
                    for c in range(self.table.columnCount())
                )
                if not match:
                    self.table.setRowHidden(r, True)
                    continue

            self.table.setRowHidden(r, False)
            visible += 1

        self.count_label.setText(f"{visible}/{total} produit(s)")

    # ------------------------------------------------------------------
    # NACRES combobox helpers
    # ------------------------------------------------------------------

    def _make_nacres_combo(self, row: int, nacres: str, color: QColor) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(_NACRES_COMBO_ITEMS)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.lineEdit().setPlaceholderText("Sélectionner ou saisir…")
        combo.setStyleSheet(f"background: {color.name()};")
        if nacres:
            label = _NACRES_LABELS.get(nacres, "")
            entry = f"{nacres} — {label}" if label else nacres
            idx = combo.findText(entry)
            if idx < 0:
                for i in range(combo.count()):
                    if combo.itemText(i).startswith(nacres):
                        idx = i
                        break
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setCurrentText(entry)
        else:
            combo.setCurrentIndex(0)
        combo.currentTextChanged.connect(
            lambda text, r=row: self._on_nacres_combo_changed(r, text)
        )
        return combo

    def _on_nacres_combo_changed(self, row: int, text: str) -> None:
        code = text.split(" — ")[0].strip().upper() if " — " in text else text.strip().upper()
        if code and code not in _NACRES_LABELS:
            code = ""

        id_item = self.table.item(row, _COL_ID)
        if not id_item:
            return
        product_id = id_item.text()

        # Mettre à jour l'item caché (utilisé par _apply_filter)
        nacres_item = self.table.item(row, _COL_NACRES)
        if nacres_item:
            self.table.blockSignals(True)
            nacres_item.setText(code)
            self.table.blockSignals(False)

        self._pending_changes[product_id] = code

        color = _COLOR_HAS_NACRES if code else _COLOR_PENDING
        self.table.blockSignals(True)
        for c in range(self.table.columnCount()):
            cell = self.table.item(row, c)
            if cell:
                cell.setBackground(color)
        self.table.blockSignals(False)
        widget = self.table.cellWidget(row, _COL_NACRES)
        if widget:
            widget.setStyleSheet(f"background: {color.name()};")

        self._update_unsaved_label()

    # ------------------------------------------------------------------
    # Édition NACRES (items directs — fallback, non-pending)
    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        pass  # NACRES pendants gérés par _on_nacres_combo_changed; autres colonnes en lecture seule

    def _auto_suggest(self) -> None:
        """Remplit les NACRES manquants par règles mots-clés (suggestions en bleu)."""
        filled = 0
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            nacres_item = self.table.item(r, _COL_NACRES)
            name_item   = self.table.item(r, _COL_NAME)
            id_item     = self.table.item(r, _COL_ID)
            if not nacres_item or not name_item or not id_item:
                continue
            if nacres_item.text().strip():
                continue  # déjà renseigné, on ne touche pas
            code, reason = suggest_nacres(name_item.text())
            if not code:
                continue
            product_id = id_item.text()
            # Mise à jour de l'item caché
            nacres_item.setText(code)
            nacres_item.setToolTip(f"Suggestion automatique : {reason}")
            # Mise à jour du QComboBox si présent (pending)
            widget = self.table.cellWidget(r, _COL_NACRES)
            if isinstance(widget, QComboBox):
                label = _NACRES_LABELS.get(code, "")
                entry = f"{code} — {label}" if label else code
                idx = widget.findText(entry)
                widget.blockSignals(True)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
                else:
                    widget.setCurrentText(entry)
                widget.blockSignals(False)
                widget.setToolTip(f"Suggestion automatique : {reason}")
            # Couleur bleu clair = suggestion
            for c in range(self.table.columnCount()):
                cell = self.table.item(r, c)
                if cell:
                    cell.setBackground(_COLOR_SUGGESTION)
            if widget:
                widget.setStyleSheet(f"background: {_COLOR_SUGGESTION.name()};")
            self._pending_changes[product_id] = code
            filled += 1
        self.table.blockSignals(False)
        # Basculer en "En attente" pour que les suggestions soient visibles
        self.show_combo.blockSignals(True)
        self.show_combo.setCurrentIndex(self.show_combo.findData("pending"))
        self.show_combo.blockSignals(False)
        self._apply_filter()
        self._update_unsaved_label()
        QMessageBox.information(
            self, "Suggestions NACRES",
            f"{filled} code(s) NACRES suggérés (en bleu).\n"
            "Vérifiez les suggestions puis cliquez sur Sauvegarder."
        )

    def _update_unsaved_label(self) -> None:
        n = len(self._pending_changes)
        if n:
            self.unsaved_label.setText(f"  {n} modification(s) non sauvegardée(s)")
            self.btn_save.setEnabled(True)
        else:
            self.unsaved_label.setText("")
            self.btn_save.setEnabled(False)

    def _set_all_checks(self, state: bool) -> None:
        self.table.blockSignals(True)
        cs = Qt.CheckState.Checked if state else Qt.CheckState.Unchecked
        for r in range(self.table.rowCount()):
            if self.table.isRowHidden(r):
                continue
            chk = self.table.item(r, _COL_CHK)
            if chk and (chk.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                chk.setCheckState(cs)
        self.table.blockSignals(False)

    # ------------------------------------------------------------------
    # Sauvegarde
    # ------------------------------------------------------------------

    def _save(self) -> None:
        if not self._pending_changes:
            return
        try:
            conn = sqlite3.connect(self.db_path)
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            for product_id, nacres in self._pending_changes.items():
                conn.execute(
                    "UPDATE commercial_products SET code_nacres = ?, updated_at = ? WHERE id = ?",
                    (nacres or None, now, product_id),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder : {e}")
            return

        n = len(self._pending_changes)
        self._pending_changes = {}
        self._update_unsaved_label()
        QMessageBox.information(self, "Sauvegardé", f"{n} code(s) NACRES mis à jour.")

    def _promote_to_draft(self) -> None:
        # Récupérer les IDs cochés (seulement les lignes visibles et cochées)
        checked_ids: set[str] = set()
        for r in range(self.table.rowCount()):
            chk = self.table.item(r, _COL_CHK)
            id_item = self.table.item(r, _COL_ID)
            if (chk and id_item
                    and (chk.flags() & Qt.ItemFlag.ItemIsUserCheckable)
                    and chk.checkState() == Qt.CheckState.Checked):
                checked_ids.add(id_item.text())

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, code_nacres FROM commercial_products WHERE status = 'pending'"
            ).fetchall()
            if checked_ids:
                promotable = [
                    r for r in rows
                    if r["id"] in checked_ids and r["code_nacres"] and r["code_nacres"].strip()
                ]
            else:
                promotable = [r for r in rows if r["code_nacres"] and r["code_nacres"].strip()]
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de lire la base : {e}")
            return

        if not promotable:
            msg = (
                "Les produits cochés n'ont pas de code NACRES.\n"
                "Assignez des NACRES avant de promouvoir."
                if checked_ids else
                "Aucun produit pending n'a de code NACRES.\n"
                "Assignez des NACRES avant de promouvoir."
            )
            QMessageBox.information(self, "Rien à faire", msg)
            return

        if self._pending_changes:
            reply = QMessageBox.question(
                self, "Modifications non sauvegardées",
                "Des modifications NACRES ne sont pas encore sauvegardées.\n"
                "Sauvegarder et promouvoir quand même ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._save()

        scope = f"les {len(promotable)} produit(s) cochés" if checked_ids else f"{len(promotable)} produit(s)"
        reply = QMessageBox.question(
            self, "Confirmer",
            f"Passer {scope} avec NACRES en statut 'draft' ?\n"
            "Ils apparaîtront ensuite dans l'onglet Validation.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            conn = sqlite3.connect(self.db_path)
            ids = [r["id"] for r in promotable]
            conn.executemany(
                "UPDATE commercial_products SET status = 'draft', updated_at = ? WHERE id = ?",
                [(now, pid) for pid in ids],
            )
            conn.commit()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de promouvoir : {e}")
            return

        QMessageBox.information(
            self, "Succès",
            f"{len(promotable)} produit(s) passés en 'draft'.\n"
            "Ouvrez l'onglet Validation pour les valider."
        )
        self._load()


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
        self.tab_validate  = ValidationTab(self.db_path)
        self.tab_merge     = MergeTab(self.db_path)
        self.tab_quality   = QualityTab(self.db_path)
        self.tab_catalogue = CatalogueTab(self.db_path)
        self.tabs.addTab(self.tab_validate,  "Validation")
        self.tabs.addTab(self.tab_merge,     "Fusion / Conflits")
        self.tabs.addTab(self.tab_quality,   "Qualite")
        self.tabs.addTab(self.tab_catalogue, "Catalogue fournisseurs")
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
        self.tab_catalogue.reload(self.db_path)


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
