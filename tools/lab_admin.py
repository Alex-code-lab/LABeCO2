# SPDX-License-Identifier: GPL-3.0-or-later
"""
LABeCO2 — Outil d'administration des bases de données.

Lance une application Qt indépendante avec trois onglets :
  1. Validation   — valider ou rejeter les entrées à valider
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

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
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
from ui.nacres_metadata import load_nacres_options
from tools.admin.catalogue_import import (
    apply_catalogue_import,
    format_preview_summary,
    preview_catalogue_import,
)
from tools.admin.merge_analyzer import (
    IMPORTABLE_KINDS,
    classify_index,
    payload_index as admin_payload_index,
    sqlite_index as admin_sqlite_index,
)
from tools.admin.workflow import (
    format_issues as format_admin_issues,
    promote_pending_products,
)


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
        product_prefill = None
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                if table == "materials":
                    r = conn.execute(
                        "SELECT emission_factor_id FROM materials WHERE id = ?", (row_id,)
                    ).fetchone()
                    if r and r[0]:
                        factor_id = r[0]
                elif table == "commercial_products":
                    r = conn.execute(
                        "SELECT code_nacres, name, product_type FROM commercial_products WHERE id = ?",
                        (row_id,),
                    ).fetchone()
                    if r:
                        product_prefill = dict(r)
        except Exception:
            pass

        win = DataMassWindow(
            parent=self,
            base_path=str(ROOT),
            user_path=str(ROOT),
            mode_filter="consumable" if table == "commercial_products" else "factor",
            sqlite_path=self.db_path,
        )
        if product_prefill:
            win.prefill_consumable(
                product_prefill.get("code_nacres") or "",
                product_prefill.get("name") or "",
                source="liquid" if product_prefill.get("product_type") == "liquid" else "solid",
            )
        else:
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
_STATUS_LABEL = {
    "pending": "En attente",
    "draft": "À valider",
    "validated": "Validé",
    "deprecated": "Déprécié",
}
_PRODUCT_TYPE_LABEL = {
    "solid": "Solide",
    "liquid": "Liquide",
    "material": "Matériau",
    "transport": "Transport",
    "spend": "Achat",
}
_MERGE_KIND_LABEL = {
    "NOUVEAU": "Nouveau",
    "DEPENDANCE": "Dépendance",
    "CONFLIT_ID": "Conflit d'identifiant",
    "DOUBLON_METIER": "Doublon métier",
    "NON_VALIDE_DES_DEUX_COTES": "Non validé des deux côtés",
    "REVISION_POSSIBLE": "Révision possible",
    "IDENTIQUE": "Identique",
    "CONFLIT": "Conflit",
    "DOUBLON": "Doublon",
}
_SEVERITY_LABEL = {
    "ERROR": "Erreur",
    "WARNING": "Avertissement",
    "INFO": "Info",
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
    "DEPENDANCE": QColor(225, 245, 254),
    "CONFLIT_ID":   QColor(255, 243, 178),
    "DOUBLON_METIER":   QColor(255, 220, 180),
    "NON_VALIDE_DES_DEUX_COTES": QColor(255, 205, 210),
    "REVISION_POSSIBLE": QColor(255, 236, 179),
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


def _status_label(status: str) -> str:
    return _STATUS_LABEL.get(str(status or ""), str(status or ""))


def _product_type_label(value: str) -> str:
    return _PRODUCT_TYPE_LABEL.get(str(value or ""), str(value or ""))


def _merge_kind_label(kind: str) -> str:
    return _MERGE_KIND_LABEL.get(str(kind or ""), str(kind or ""))


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
        self._ref_index = admin_sqlite_index(self.ref_path)
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
        full_index = admin_payload_index(payload)
        self._source_indexes[source_key] = full_index
        selected_index = self._selected_rows_from_index(full_index, source["tables"])
        return self._classifications_to_entries(source, source_key, selected_index)

    def _analyze_sqlite(self, source: dict) -> list[dict]:
        source_key = source["key"]
        full_index = admin_sqlite_index(source["path"])
        self._source_indexes[source_key] = full_index
        selected_index = self._selected_rows_from_index(full_index, source["tables"])
        return self._classifications_to_entries(source, source_key, selected_index)

    def _classifications_to_entries(
        self,
        source: dict,
        source_key: str,
        selected_index: dict[str, dict[str, dict]],
    ) -> list[dict]:
        results = []
        for classification in classify_index(selected_index, self._ref_index):
            entry = classification.to_entry()
            entry.update({
                "label": _entry_label(entry["table"], entry["data"], self._source_indexes[source_key]),
                "source_key": source_key,
                "source_label": f"{source['path'].name} [{source['scope']}]",
                "source_path": str(source["path"]),
            })
            results.append(entry)
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
            type_value = _product_type_label(data.get("factor_type") or "")
            factor_text = data.get("name") or ""
            co2 = data.get("co2_factor")
            unit = data.get("co2_unit") or "kgCO2e/kg"
            co2_text = "" if co2 is None else f"{_fmt_number(co2)} {unit}"
        elif table == "materials":
            type_value = _product_type_label("material")
            factor_text, co2_text = self._factor_summary(entry, data.get("emission_factor_id"))
        elif table == "commercial_products":
            type_value = _product_type_label(data.get("product_type") or "")
            packaging_count = _fmt_number(data.get("units_per_sold_packaging"))
            if data.get("product_type") == "liquid":
                factor_text, co2_text = self._factor_summary(entry, data.get("emission_factor_id"))
            else:
                factor_text, _ = self._product_components_summary(entry, data.get("id", ""))
        elif table == "product_components":
            product = self._lookup(entry, "commercial_products", data.get("product_id"))
            nacres = product.get("code_nacres") or ""
            type_value = _product_type_label(product.get("product_type") or "")
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
            _merge_kind_label(entry["kind"]),
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
            _status_label(data.get("status", "")),
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
        n_conf = sum(1 for e in self._entries if e["kind"] in {"CONFLIT_ID", "NON_VALIDE_DES_DEUX_COTES"})
        n_dup  = sum(1 for e in self._entries if e["kind"] == "DOUBLON_METIER")
        n_rev  = sum(1 for e in self._entries if e["kind"] == "REVISION_POSSIBLE")
        self.diff_view.setPlaceholderText(
            f"Analyse : {n} différences  |  {n_new} nouveaux  |  "
            f"{n_conf} conflits  |  {n_dup} doublons  |  {n_rev} révisions possibles"
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
            f"[{_merge_kind_label(entry['kind'])}]  {_TABLE_LABEL.get(table, table)}  -  {entry['label']}",
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
        if entry.get("reason"):
            lines.extend(["", f"Décision : {entry['reason']}"])
        if entry["kind"] not in IMPORTABLE_KINDS:
            lines.append("Cette ligne n'est pas importable automatiquement.")
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
        blocked = [entry for entry in entries if entry["kind"] not in IMPORTABLE_KINDS]
        if blocked:
            details = "\n".join(
                f"- {_merge_kind_label(entry['kind'])} [{_TABLE_LABEL.get(entry['table'], entry['table'])}] "
                f"{entry.get('label') or entry.get('id')}"
                for entry in blocked[:20]
            )
            QMessageBox.warning(
                self,
                "Import bloqué",
                "La sélection contient des conflits ou doublons qui demandent une décision manuelle.\n"
                "Aucune entrée existante ne sera écrasée automatiquement.\n\n"
                f"{details}",
            )
            return

        msg = f"Importer {len(entries)} entrée(s) nouvelle(s) ou dépendance(s) dans la base de référence ?"
        reply = QMessageBox.question(self, "Confirmer l'import", msg,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._ref_index = admin_sqlite_index(self.ref_path)
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

        headers = ["Sévérité", "Table", "Message", "Entrée", "Détail"]
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
            values = [
                _SEVERITY_LABEL.get(issue.severity, issue.severity),
                _TABLE_LABEL.get(issue.table, issue.table),
                issue.message,
                issue.entry,
                issue.detail,
            ]
            for c, val in enumerate(values):
                item = QTableWidgetItem(str(val or ""))
                if c == 2 and issue.rule:
                    item.setToolTip(issue.rule)
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
_COLOR_NACRES_NEW_NO_FE = QColor(255, 210, 150)  # orange : nouveau NACRES sans FE achats
_NACRES_NEW_NO_FE_TOOLTIP = (
    "Nouveau code NACRES 2026 : le projet GES 1point5 n'a pas encore défini "
    "de facteur d'émission pour cette catégorie."
)


def suggest_nacres(name: str) -> tuple[str, str]:
    """Retourne (nacres_code, raison) depuis le nom du produit, ou ('', '') si inconnu."""
    name_l = name.lower()
    for keywords, code, reason in _NACRES_RULES:
        if any(kw in name_l for kw in keywords):
            return code, reason
    return "", ""


# ============================================================
# Onglet 4 — Catalogue fournisseurs (assignation NACRES)
# ============================================================

_COL_CHK     = 0   # checkbox (cocher pour sélectionner)
_COL_ID      = 1   # hidden product id
_COL_SUPPL   = 2
_COL_DATE    = 3
_COL_CODE    = 4   # code fournisseur (ex: A0602.0100 Duchefa, 08-212 IJM)
_COL_NAME    = 5
_COL_BRAND   = 6
_COL_CONDT   = 7
_COL_PRICE   = 8
_COL_TYPE    = 9
_COL_NACRES  = 10  # QComboBox pour les lignes en attente, lecture seule sinon
_COL_STATUS  = 11

_CATALOGUE_HEADERS = [
    "", "id", "Fournisseur", "Version", "Code catalogue", "Désignation", "Marque",
    "Conditionnement", "Prix HT (€)", "Type", "Code NACRES", "Statut",
]

_COLOR_PENDING    = QColor(255, 243, 180)   # jaune : en attente de validation
_COLOR_HAS_NACRES = QColor(210, 240, 210)   # vert  : NACRES confirmé
_COLOR_VALIDATED  = QColor(220, 235, 255)   # bleu clair : déjà validé


def _combo_stylesheet(color: QColor) -> str:
    return f"""
        QComboBox, QComboBox QLineEdit {{
            background: {color.name()};
            color: black;
        }}
        QComboBox QAbstractItemView {{
            background: white;
            color: black;
            selection-background-color: #d7ebff;
            selection-color: black;
        }}
    """


class _NacresPrefixFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._prefix = ""

    def set_prefix(self, text: str) -> None:
        prefix = (text or "").strip().upper()
        if prefix == self._prefix:
            return
        self._prefix = prefix
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._prefix:
            return True
        source_model = self.sourceModel()
        if source_model is None:
            return False
        index = source_model.index(source_row, 0, source_parent)
        code = str(source_model.data(index, Qt.ItemDataRole.UserRole) or "").upper()
        return bool(code) and code.startswith(self._prefix)


class CatalogueTab(QWidget):
    """Onglet d'assignation des codes NACRES aux produits importés en attente."""

    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = db_path
        self._pending_changes: dict[str, str] = {}   # product_id → new nacres
        self._nacres_options = []
        self._nacres_by_code = {}
        self._nacres_model = QStandardItemModel(self)
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

        filter_bar.addWidget(QLabel("  Version :"))
        self.catalogue_date_combo = QComboBox()
        self.catalogue_date_combo.addItem("Toutes", "")
        self.catalogue_date_combo.currentIndexChanged.connect(self._apply_filter)
        filter_bar.addWidget(self.catalogue_date_combo)

        filter_bar.addWidget(QLabel("  Afficher :"))
        self.show_combo = QComboBox()
        self.show_combo.addItem("En attente", "pending")
        self.show_combo.addItem("Sans NACRES seulement", "missing")
        self.show_combo.addItem("Nouveaux NACRES sans FE", "new_no_fe")
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

        btn_import_catalogue = QPushButton("Importer un catalogue…")
        btn_import_catalogue.clicked.connect(self._import_catalogue)
        filter_bar.addWidget(btn_import_catalogue)

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
            ("Nouveau sans FE Labo1point5", _COLOR_NACRES_NEW_NO_FE),
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
        self.table.setColumnWidth(_COL_NACRES, 260)
        self.table.horizontalHeader().setSectionResizeMode(
            _COL_CHK, QHeaderView.ResizeMode.Fixed
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            _COL_CHK, QHeaderView.ResizeMode.Fixed
        )
        self.table.horizontalHeader().setSectionResizeMode(
            _COL_NACRES, QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.cellDoubleClicked.connect(self._activate_nacres_editor)
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

        self.btn_promote = QPushButton("Passer en validation")
        self.btn_promote.setToolTip(
            "Les produits complets avec un code NACRES passent en statut « à valider »\n"
            "et apparaissent dans l'onglet Validation."
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

    def _import_catalogue(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Importer un catalogue fournisseur parsé",
            str(ROOT / "data" / "catalogues"),
            "Catalogues (*.csv *.xlsx *.xls);;Tous (*)",
        )
        if not path_str:
            return
        path = Path(path_str)

        supplier, ok = QInputDialog.getText(
            self,
            "Fournisseur",
            "Fournisseur à utiliser si le fichier ne contient pas de colonne fournisseur :",
        )
        if not ok:
            return
        catalogue_date, ok = QInputDialog.getText(
            self,
            "Version catalogue",
            "Version/date du catalogue à utiliser si absente du fichier :",
        )
        if not ok:
            return

        conn = sqlite3.connect(self.db_path)
        try:
            preview = preview_catalogue_import(
                conn,
                path,
                supplier_override=supplier,
                catalogue_date_override=catalogue_date,
            )
        except Exception as e:
            conn.close()
            QMessageBox.critical(self, "Erreur d'import catalogue", str(e))
            return

        details = []
        for item in preview.items:
            if item.action in {"ambiguous", "ignored"} or item.price_changed or item.packaging_changed:
                markers = [item.action]
                if item.price_changed:
                    markers.append("prix changé")
                if item.packaging_changed:
                    markers.append("conditionnement changé")
                details.append(
                    f"Ligne {item.row.row_number} [{', '.join(markers)}] "
                    f"{item.row.code_fournisseur} - {item.row.designation}: {item.reason}"
                )
        if len(details) > 80:
            details = details[:80] + [f"... {len(details) - 80} autre(s) ligne(s)"]

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Prévisualisation catalogue")
        box.setText("Importer ce catalogue dans la base de travail ?")
        box.setInformativeText(format_preview_summary(preview))
        if details:
            box.setDetailedText("\n".join(details))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            conn.close()
            return

        try:
            conn.execute("BEGIN")
            stats = apply_catalogue_import(conn, preview)
            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.close()
            QMessageBox.critical(self, "Erreur d'import catalogue", str(e))
            return
        conn.close()

        QMessageBox.information(
            self,
            "Catalogue importé",
            (
                f"{stats['inserted_catalogue']} ligne(s) catalogue insérée(s).\n"
                f"{stats['created_pending']} nouveau(x) produit(s) en attente.\n"
                f"{stats['linked']} produit(s) existant(s) lié(s)."
            ),
        )
        self._load()

    def _load(self) -> None:
        self._pending_changes = {}
        self._update_unsaved_label()

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            self._nacres_options = load_nacres_options(conn)
            self._nacres_by_code = {option.code: option for option in self._nacres_options}
            self._rebuild_nacres_model()

            rows = conn.execute("""
                SELECT
                    cp.id,
                    COALESCE(sc.supplier, ijm.source_catalogue, 'Inconnu') AS supplier,
                    COALESCE(sc.catalogue_date, '') AS catalogue_date,
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
            catalogue_dates = sorted({r["catalogue_date"] for r in rows if r["catalogue_date"]})
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

        self.catalogue_date_combo.blockSignals(True)
        current_date = self.catalogue_date_combo.currentData()
        self.catalogue_date_combo.clear()
        self.catalogue_date_combo.addItem("Toutes", "")
        for value in catalogue_dates:
            self.catalogue_date_combo.addItem(value, value)
        idx = self.catalogue_date_combo.findData(current_date)
        if idx >= 0:
            self.catalogue_date_combo.setCurrentIndex(idx)
        self.catalogue_date_combo.blockSignals(False)

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

            # Checkbox (sélection pour promotion) — uniquement pour les lignes en attente
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
            self.table.setItem(r, _COL_DATE,   _item(row["catalogue_date"]))
            self.table.setItem(r, _COL_CODE,   _item(row["code_catalogue"]))
            self.table.setItem(r, _COL_NAME,   _item(row["name"]))
            self.table.setItem(r, _COL_BRAND,  _item(row["brand"]))
            self.table.setItem(r, _COL_CONDT,  _item(row["conditionnement"]))
            price = row["price_ht"]
            self.table.setItem(r, _COL_PRICE,  _item(f"{price:.2f}" if price else ""))
            self.table.setItem(r, _COL_TYPE,   _item(_product_type_label(row["product_type"])))
            # NACRES : item texte léger. Le QComboBox est créé au double-clic.
            nacres_cell = _item(nacres)
            if is_pending:
                nacres_cell.setToolTip("Double-cliquer pour ouvrir la liste NACRES.")
            self.table.setItem(r, _COL_NACRES, nacres_cell)
            status_cell = _item(_status_label(status))
            status_cell.setData(Qt.ItemDataRole.UserRole, status)
            self.table.setItem(r, _COL_STATUS, status_cell)

        self.table.blockSignals(False)
        self._apply_filter()

    def _apply_filter(self) -> None:
        supplier_filter = self.supplier_combo.currentData() or ""
        catalogue_date_filter = self.catalogue_date_combo.currentData() or ""
        show_mode = self.show_combo.currentData()
        needle = self.search_edit.text().strip().lower()

        total = self.table.rowCount()
        visible = 0
        for r in range(total):
            supplier_item = self.table.item(r, _COL_SUPPL)
            date_item     = self.table.item(r, _COL_DATE)
            nacres_item   = self.table.item(r, _COL_NACRES)
            if not supplier_item:
                self.table.setRowHidden(r, True)
                continue

            supplier_val = supplier_item.text()
            date_val     = (date_item.text() if date_item else "").strip()
            # Pour les lignes en attente, lire la valeur depuis l'item caché (maintenu par les handlers)
            nacres_val   = (nacres_item.text() if nacres_item else "").strip()
            status_item  = self.table.item(r, _COL_STATUS)
            status_val   = (status_item.data(Qt.ItemDataRole.UserRole) if status_item else "") or ""

            if supplier_filter and supplier_val != supplier_filter:
                self.table.setRowHidden(r, True)
                continue
            if catalogue_date_filter and date_val != catalogue_date_filter:
                self.table.setRowHidden(r, True)
                continue
            if show_mode == "pending" and status_val != "pending":
                self.table.setRowHidden(r, True)
                continue
            if show_mode == "missing" and nacres_val:
                self.table.setRowHidden(r, True)
                continue
            if show_mode == "new_no_fe":
                option = self._nacres_by_code.get(nacres_val)
                if not option or not option.is_new_without_labo1point5_fe:
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

    def _activate_nacres_editor(self, row: int, column: int) -> None:
        if column != _COL_NACRES:
            return
        status_item = self.table.item(row, _COL_STATUS)
        raw_status = (status_item.data(Qt.ItemDataRole.UserRole) if status_item else "") or ""
        if raw_status != "pending":
            return
        if isinstance(self.table.cellWidget(row, _COL_NACRES), QComboBox):
            return

        nacres_item = self.table.item(row, _COL_NACRES)
        nacres = nacres_item.text().strip() if nacres_item else ""
        color = _COLOR_HAS_NACRES if nacres else _COLOR_PENDING
        if nacres_item:
            color = nacres_item.background().color()
        combo = self._make_nacres_combo(row, nacres, color)
        self.table.setCellWidget(row, _COL_NACRES, combo)
        combo.setFocus()
        combo.showPopup()

    def _nacres_display(self, code: str) -> str:
        option = self._nacres_by_code.get((code or "").strip().upper())
        if not option:
            return (code or "").strip().upper()
        return f"{option.code} — {option.label}" if option.label else option.code

    def _nacres_code_from_text(self, text: str) -> str:
        raw = (text or "").strip().upper()
        if " — " in raw:
            return raw.split(" — ", 1)[0].strip()
        if " - " in raw:
            return raw.split(" - ", 1)[0].strip()
        return raw

    def _show_short_nacres_code(self, combo: QComboBox, code: str) -> None:
        combo.blockSignals(True)
        combo.setEditText(code.strip().upper())
        combo.lineEdit().setCursorPosition(0)
        combo.blockSignals(False)

    def _filter_nacres_combo(self, combo: QComboBox, text: str) -> None:
        proxy = getattr(combo, "_nacres_proxy", None)
        if not isinstance(proxy, _NacresPrefixFilterProxy):
            return
        proxy.set_prefix(self._nacres_code_from_text(text))
        combo.lineEdit().setText(text)
        combo.lineEdit().setCursorPosition(len(text))

    def _rebuild_nacres_model(self) -> None:
        model = QStandardItemModel(self)
        empty = QStandardItem("")
        empty.setData("", Qt.ItemDataRole.UserRole)
        empty.setData(QColor(0, 0, 0), Qt.ItemDataRole.ForegroundRole)
        model.appendRow(empty)
        for option in self._nacres_options:
            item = QStandardItem(self._nacres_display(option.code))
            item.setData(option.code, Qt.ItemDataRole.UserRole)
            item.setData(QColor(0, 0, 0), Qt.ItemDataRole.ForegroundRole)
            if option.is_new_without_labo1point5_fe:
                item.setData(_COLOR_NACRES_NEW_NO_FE, Qt.ItemDataRole.BackgroundRole)
                item.setData(_NACRES_NEW_NO_FE_TOOLTIP, Qt.ItemDataRole.ToolTipRole)
            model.appendRow(item)
        self._nacres_model = model

    def _make_nacres_combo(self, row: int, nacres: str, color: QColor) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setMinimumWidth(260)
        combo.view().setMinimumWidth(560)
        proxy = _NacresPrefixFilterProxy(combo)
        proxy.setSourceModel(self._nacres_model)
        combo._nacres_proxy = proxy
        combo.setModel(proxy)
        combo.setCompleter(None)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.lineEdit().setPlaceholderText("Sélectionner ou saisir…")
        combo.lineEdit().setCompleter(None)
        combo.setStyleSheet(_combo_stylesheet(color))
        if nacres:
            nacres = nacres.strip().upper()
            entry = self._nacres_display(nacres)
            idx = combo.findData(nacres)
            if idx < 0:
                for i in range(combo.count()):
                    if combo.itemText(i).startswith(nacres):
                        idx = i
                        break
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setCurrentText(entry)
            self._show_short_nacres_code(combo, nacres)
        else:
            combo.setCurrentIndex(0)
        combo.lineEdit().textEdited.connect(
            lambda text, c=combo: self._filter_nacres_combo(c, text)
        )
        combo.activated.connect(
            lambda _index, r=row, c=combo: self._on_nacres_combo_changed(r, c.currentText())
        )
        combo.lineEdit().editingFinished.connect(
            lambda r=row, c=combo: self._on_nacres_combo_changed(r, c.currentText())
        )
        return combo

    def _on_nacres_combo_changed(self, row: int, text: str) -> None:
        code = self._nacres_code_from_text(text)
        if code and code not in self._nacres_by_code:
            return

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
            widget.setStyleSheet(_combo_stylesheet(color))
        if isinstance(widget, QComboBox):
            self._show_short_nacres_code(widget, code)

        self._update_unsaved_label()

    # ------------------------------------------------------------------
    # Édition NACRES (items directs — fallback, hors lignes en attente)
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
            if code not in self._nacres_by_code:
                continue
            product_id = id_item.text()
            # Mise à jour de l'item caché
            nacres_item.setText(code)
            nacres_item.setToolTip(f"Suggestion automatique : {reason}")
            # Mise à jour du QComboBox si présent (ligne en attente)
            widget = self.table.cellWidget(r, _COL_NACRES)
            if isinstance(widget, QComboBox):
                proxy = getattr(widget, "_nacres_proxy", None)
                if isinstance(proxy, _NacresPrefixFilterProxy):
                    proxy.set_prefix("")
                entry = self._nacres_display(code)
                idx = widget.findData(code)
                widget.blockSignals(True)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
                else:
                    widget.setCurrentText(entry)
                widget.setEditText(code)
                widget.lineEdit().setCursorPosition(0)
                widget.blockSignals(False)
                widget.setToolTip(f"Suggestion automatique : {reason}")
            # Couleur bleu clair = suggestion
            for c in range(self.table.columnCount()):
                cell = self.table.item(r, c)
                if cell:
                    cell.setBackground(_COLOR_SUGGESTION)
            if widget:
                widget.setStyleSheet(_combo_stylesheet(_COLOR_SUGGESTION))
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

        try:
            conn = sqlite3.connect(self.db_path)
            preview = promote_pending_products(conn, checked_ids or None)
            conn.rollback()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de contrôler les produits : {e}")
            return

        if not preview.promoted:
            all_issues = [issue for issues in preview.blocked.values() for issue in issues]
            msg = "Aucun produit en attente n'est prêt à passer en validation."
            if all_issues:
                msg += "\n\n" + format_admin_issues(all_issues)
            QMessageBox.information(self, "Rien à faire", msg)
            return

        scope = f"les {len(preview.promoted)} produit(s) cochés" if checked_ids else f"{len(preview.promoted)} produit(s)"
        reply = QMessageBox.question(
            self, "Confirmer",
            f"Passer {scope} avec NACRES en validation ?\n"
            "Ils apparaîtront ensuite dans l'onglet Validation.\n\n"
            f"{len(preview.blocked)} produit(s) bloqué(s) par les règles qualité.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            conn = sqlite3.connect(self.db_path)
            result = promote_pending_products(conn, checked_ids or None)
            conn.commit()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de promouvoir : {e}")
            return

        QMessageBox.information(
            self, "Succès",
            f"{len(result.promoted)} produit(s) passés en validation.\n"
            f"{len(result.blocked)} produit(s) laissé(s) en attente.\n"
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
