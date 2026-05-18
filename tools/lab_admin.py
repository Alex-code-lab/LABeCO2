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

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
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

from ui.validate_window import ValidateWidget, TABLES_META
from ui.quality_check import check_database, format_issues


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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

_MERGE_TABLES = list(TABLES_META.keys())
_NAME_COL = {
    "emission_factors": "name",
    "materials": "name",
    "commercial_products": "name",
    "transport_factors": "origin",
}

_SEV_COLOR = {
    "NOUVEAU":   QColor(213, 245, 213),
    "CONFLIT":   QColor(255, 243, 178),
    "DOUBLON":   QColor(255, 220, 180),
}


def _rows_as_dict(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    conn.row_factory = sqlite3.Row
    return {r["id"]: dict(r) for r in conn.execute(f"SELECT * FROM {table}")}


def _diff_fields(a: dict, b: dict, skip=("updated_at", "created_at")) -> list[str]:
    diffs = []
    for k in set(a) | set(b):
        if k in skip:
            continue
        if a.get(k) != b.get(k):
            diffs.append(f"  {k}: {a.get(k)!r}  →  {b.get(k)!r}")
    return diffs


class MergeTab(QWidget):
    def __init__(self, ref_path: Path):
        super().__init__()
        self.ref_path = ref_path
        self.contrib_path: Path | None = None
        self._entries: list[dict] = []   # analysed entries
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # Sélection du fichier de contribution
        src_bar = QHBoxLayout()
        src_bar.addWidget(QLabel("Contribution :"))
        self.src_label = QLabel("(aucun fichier sélectionné)")
        self.src_label.setStyleSheet("color: #888;")
        src_bar.addWidget(self.src_label, 1)
        btn_open = QPushButton("Ouvrir…")
        btn_open.setMaximumWidth(90)
        btn_open.clicked.connect(self._open_contribution)
        src_bar.addWidget(btn_open)
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

    def _open_contribution(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner la contribution",
            str(ROOT),
            "SQLite / JSON (*.sqlite *.db *.json);;Tous (*)",
        )
        if not path:
            return
        self.contrib_path = Path(path)
        self.src_label.setText(self.contrib_path.name)
        self.src_label.setStyleSheet("color: #333;")
        self.btn_analyze.setEnabled(True)

    def _analyze(self) -> None:
        if not self.contrib_path:
            return
        self._entries = []
        try:
            if self.contrib_path.suffix == ".json":
                self._entries = self._analyze_json()
            else:
                self._entries = self._analyze_sqlite()
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'analyse", str(e))
            return
        self._populate_table()

    def _analyze_json(self) -> list[dict]:
        with open(self.contrib_path, encoding="utf-8") as f:
            payload = json.load(f)
        ref_conn = sqlite3.connect(self.ref_path)
        ref_conn.row_factory = sqlite3.Row
        results = []
        for entry in payload.get("entries", []):
            table = entry.get("table")
            data  = entry.get("data", {})
            if table not in _MERGE_TABLES + ["product_components", "sources", "contributors"]:
                continue
            eid = data.get("id", "")
            name_col = _NAME_COL.get(table, "id")
            label = data.get(name_col) or eid
            existing = ref_conn.execute(
                f"SELECT * FROM {table} WHERE id = ?", (eid,)
            ).fetchone() if table not in ("sources", "contributors") else None

            if existing is None:
                kind = "NOUVEAU"
                diffs = []
            else:
                diffs = _diff_fields(dict(existing), data)
                kind = "CONFLIT" if diffs else None
            if kind:
                results.append({"kind": kind, "table": table, "id": eid,
                                 "label": label, "data": data,
                                 "existing": dict(existing) if existing else {},
                                 "diffs": diffs})
        ref_conn.close()
        # Chercher doublons de nom dans la référence
        self._flag_name_duplicates(results)
        return results

    def _analyze_sqlite(self) -> list[dict]:
        ref_conn  = sqlite3.connect(self.ref_path)
        cont_conn = sqlite3.connect(self.contrib_path)
        results   = []
        for table in _MERGE_TABLES:
            try:
                ref_rows  = _rows_as_dict(ref_conn, table)
                cont_rows = _rows_as_dict(cont_conn, table)
            except Exception:
                continue
            name_col = _NAME_COL.get(table, "id")
            for eid, cont_data in cont_rows.items():
                label = cont_data.get(name_col) or eid
                if eid not in ref_rows:
                    kind = "NOUVEAU"
                    diffs = []
                else:
                    diffs = _diff_fields(ref_rows[eid], cont_data)
                    kind = "CONFLIT" if diffs else None
                if kind:
                    results.append({"kind": kind, "table": table, "id": eid,
                                     "label": label, "data": cont_data,
                                     "existing": ref_rows.get(eid, {}),
                                     "diffs": diffs})
        ref_conn.close()
        cont_conn.close()
        self._flag_name_duplicates(results)
        return results

    def _flag_name_duplicates(self, results: list[dict]) -> None:
        """Marque DOUBLON les entrées nouvelles dont le nom existe déjà (ID différent)."""
        ref_conn = sqlite3.connect(self.ref_path)
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
            row = ref_conn.execute(
                f"SELECT id FROM {table} WHERE lower(trim({name_col})) = lower(trim(?))",
                (label,)
            ).fetchone()
            if row and row[0] != entry["id"]:
                entry["kind"] = "DOUBLON"
                entry["diffs"] = [f"  ID existant : {row[0]}"]
        ref_conn.close()

    def _populate_table(self) -> None:
        headers = ["", "Type", "Table", "Nom / Origine", "Statut source"]
        self.table.blockSignals(True)
        self.table.clearContents()
        self.table.setRowCount(len(self._entries))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setColumnWidth(0, 28)

        for r, entry in enumerate(self._entries):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            chk.setData(Qt.ItemDataRole.UserRole, r)
            color = _SEV_COLOR.get(entry["kind"], QColor(255, 255, 255))
            chk.setBackground(color)
            self.table.setItem(r, 0, chk)

            for c, val in enumerate([entry["kind"], entry["table"],
                                      entry["label"],
                                      entry["data"].get("status", "")]):
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
        lines = [f"[{entry['kind']}]  {entry['table']}  —  {entry['label']}"]
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
            conn = sqlite3.connect(self.ref_path)
            conn.execute("PRAGMA foreign_keys = ON")
            imported = 0
            for entry in entries:
                table = entry["table"]
                data  = entry["data"]
                cols  = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
                values = {c: data.get(c) for c in cols if c in data}
                values["updated_at"] = _now()
                col_names    = ", ".join(values.keys())
                placeholders = ", ".join("?" * len(values))
                set_clause   = ", ".join(f"{k} = ?" for k in values)
                conn.execute(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) "
                    f"ON CONFLICT(id) DO UPDATE SET {set_clause}",
                    list(values.values()) + list(values.values()),
                )
                imported += 1
            conn.commit()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'import", str(e))
            return
        QMessageBox.information(self, "Import terminé", f"{imported} entrée(s) importée(s).")
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
        print("Créez d'abord la base avec : python tools/migrate_hdf5_to_sqlite.py", file=sys.stderr)
        sys.exit(1)

    app = QApplication.instance() or QApplication(sys.argv)
    win = AdminWindow(db_path)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
