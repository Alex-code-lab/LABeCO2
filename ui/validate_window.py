# SPDX-License-Identifier: GPL-3.0-or-later
"""Fenêtre de validation des entrées draft pour le mainteneur LABeCO2."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_BLACK = QColor(0, 0, 0)

_COLOR_WARN      = QColor(255, 243, 180)   # jaune  : draft sans source
_COLOR_OK        = QColor(210, 240, 210)   # vert   : draft avec source
_COLOR_VALIDATED = QColor(200, 225, 255)   # bleu   : validé
_COLOR_DEPRECATED = QColor(220, 220, 220)  # gris   : déprécié


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _item(text: str, bg: QColor | None = None) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text) if text is not None else "")
    it.setForeground(_BLACK)
    if bg:
        it.setBackground(bg)
    return it


def _row_color(status: str, has_source: bool) -> QColor:
    if status == "validated":
        return _COLOR_VALIDATED
    if status == "deprecated":
        return _COLOR_DEPRECATED
    return _COLOR_OK if has_source else _COLOR_WARN


# Les requêtes incluent toujours status AS "Statut" et utilisent {where}.
TABLES_META = {
    "emission_factors": {
        "label": "Facteurs d'émission",
        "alias": "ef",
        "query_tpl": """
            SELECT ef.id, ef.status AS "Statut", ef.name AS "Nom", ef.factor_type AS "Type",
                   ef.co2_factor AS "CO₂", ef.uncertainty AS "Incert.",
                   s.title AS "Source",
                   c.name AS "Ajouté par", v.name AS "Validé par",
                   ef.created_at AS "Créé le"
            FROM emission_factors ef
            LEFT JOIN sources s ON s.id = ef.source_id
            LEFT JOIN contributors c ON c.id = ef.contributor_id
            LEFT JOIN contributors v ON v.id = ef.validated_by_id
            {where}
            ORDER BY ef.name
        """,
        "summary_tpl": """
            SELECT ef.id, ef.status AS "Statut", ef.name AS "Nom",
                   s.title AS "Source", c.name AS "Contributeur", ef.created_at AS "Créé le"
            FROM emission_factors ef
            LEFT JOIN sources s ON s.id = ef.source_id
            LEFT JOIN contributors c ON c.id = ef.contributor_id
            {where}
            ORDER BY ef.name
        """,
    },
    "materials": {
        "label": "Matériaux",
        "alias": "m",
        "query_tpl": """
            SELECT m.id, m.status AS "Statut", m.name AS "Nom", ef.co2_factor AS "CO₂",
                   s.title AS "Source",
                   c.name AS "Ajouté par", v.name AS "Validé par",
                   m.created_at AS "Créé le"
            FROM materials m
            LEFT JOIN emission_factors ef ON ef.id = m.emission_factor_id
            LEFT JOIN sources s ON s.id = m.source_id
            LEFT JOIN contributors c ON c.id = m.contributor_id
            LEFT JOIN contributors v ON v.id = m.validated_by_id
            {where}
            ORDER BY m.name
        """,
        "summary_tpl": """
            SELECT m.id, m.status AS "Statut", m.name AS "Nom",
                   s.title AS "Source", c.name AS "Contributeur", m.created_at AS "Créé le"
            FROM materials m
            LEFT JOIN sources s ON s.id = m.source_id
            LEFT JOIN contributors c ON c.id = m.contributor_id
            {where}
            ORDER BY m.name
        """,
    },
    "commercial_products": {
        "label": "Produits commerciaux",
        "alias": "cp",
        # Facteur direct = emission_factor_id (liquides uniquement).
        # Composants = nb de matériaux liés via product_components (solides).
        "query_tpl": """
            SELECT cp.id, cp.status AS "Statut", cp.name AS "Nom", cp.code_nacres AS "NACRES",
                   cp.product_type AS "Type", cp.price_sold_packaging AS "Prix (€)",
                   CASE WHEN cp.product_type = 'liquid'
                        THEN COALESCE(ef.name, '⚠ manquant')
                        ELSE NULL
                   END AS "Facteur direct",
                   (SELECT COUNT(*) FROM product_components pc
                    WHERE pc.product_id = cp.id) AS "Composants",
                   s.title AS "Source",
                   c.name AS "Ajouté par", v.name AS "Validé par",
                   cp.created_at AS "Créé le"
            FROM commercial_products cp
            LEFT JOIN emission_factors ef ON ef.id = cp.emission_factor_id
            LEFT JOIN sources s ON s.id = cp.source_id
            LEFT JOIN contributors c ON c.id = cp.contributor_id
            LEFT JOIN contributors v ON v.id = cp.validated_by_id
            {where}
            ORDER BY cp.code_nacres, cp.name
        """,
        "summary_tpl": """
            SELECT cp.id, cp.status AS "Statut", cp.name AS "Nom",
                   s.title AS "Source", c.name AS "Contributeur", cp.created_at AS "Créé le"
            FROM commercial_products cp
            LEFT JOIN sources s ON s.id = cp.source_id
            LEFT JOIN contributors c ON c.id = cp.contributor_id
            {where}
            ORDER BY cp.code_nacres, cp.name
        """,
    },
    "transport_factors": {
        "label": "Facteurs transport",
        "alias": "tf",
        "query_tpl": """
            SELECT tf.id, tf.status AS "Statut", tf.origin AS "Origine", tf.mode AS "Mode",
                   tf.factor_kgco2e_per_kg AS "Facteur", tf.uncertainty AS "Incert.",
                   s.title AS "Source",
                   c.name AS "Ajouté par", v.name AS "Validé par",
                   tf.created_at AS "Créé le"
            FROM transport_factors tf
            LEFT JOIN sources s ON s.id = tf.source_id
            LEFT JOIN contributors c ON c.id = tf.contributor_id
            LEFT JOIN contributors v ON v.id = tf.validated_by_id
            {where}
            ORDER BY tf.origin
        """,
        "summary_tpl": """
            SELECT tf.id, tf.status AS "Statut", tf.origin AS "Nom",
                   s.title AS "Source", c.name AS "Contributeur", tf.created_at AS "Créé le"
            FROM transport_factors tf
            LEFT JOIN sources s ON s.id = tf.source_id
            LEFT JOIN contributors c ON c.id = tf.contributor_id
            {where}
            ORDER BY tf.origin
        """,
    },
}

# Colonnes fixes pour la vue "Toutes les tables" (inclut Statut)
_SUMMARY_HEADERS = ["Statut", "Nom", "Source", "Contributeur", "Créé le"]


class ValidateWidget(QWidget):
    """Widget de validation embarquable (onglet ou fenêtre standalone)."""

    validated = Signal()

    def __init__(self, sqlite_path: str | Path, show_close: bool = True, parent=None):
        super().__init__(parent)
        self.sqlite_path = Path(sqlite_path)
        self._show_close = show_close
        self._build_ui()
        self._load_table()

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # Filtre table + statut
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Table :"))
        self.table_combo = QComboBox()
        self.table_combo.addItem("Toutes les tables", "all")
        for key, meta in TABLES_META.items():
            self.table_combo.addItem(meta["label"], key)
        self.table_combo.currentIndexChanged.connect(self._load_table)
        filter_bar.addWidget(self.table_combo)

        filter_bar.addWidget(QLabel("  Statut :"))
        self.status_combo = QComboBox()
        self.status_combo.addItem("Drafts en attente", "draft")
        self.status_combo.addItem("Tous les statuts", "all")
        self.status_combo.currentIndexChanged.connect(self._load_table)
        filter_bar.addWidget(self.status_combo)

        filter_bar.addSpacing(12)
        filter_bar.addWidget(QLabel("Recherche :"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filtrer les lignes…")
        self.search_edit.setMinimumWidth(220)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._filter_rows)
        filter_bar.addWidget(self.search_edit)

        filter_bar.addStretch()
        self.count_label = QLabel("")
        filter_bar.addWidget(self.count_label)
        root.addLayout(filter_bar)

        # Légende couleurs
        self.legend_bar = QHBoxLayout()
        root.addLayout(self.legend_bar)
        self._refresh_legend()

        # Tableau
        self.table_widget = QTableWidget()
        self.table_widget.setAlternatingRowColors(False)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_widget.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table_widget)

        # Sélection
        sel_bar = QHBoxLayout()
        btn_all  = QPushButton("Tout cocher")
        btn_none = QPushButton("Tout décocher")
        btn_all.clicked.connect(self._check_all)
        btn_none.clicked.connect(self._uncheck_all)
        sel_bar.addWidget(btn_all)
        sel_bar.addWidget(btn_none)
        sel_bar.addStretch()
        self.sel_count_label = QLabel("0 sélectionné(e)s")
        sel_bar.addWidget(self.sel_count_label)
        root.addLayout(sel_bar)

        # Validateur : combo existants + saisie libre
        validator_bar = QHBoxLayout()
        validator_bar.addWidget(QLabel("Validateur :"))
        self.validator_combo = QComboBox()
        self.validator_combo.setEditable(True)
        self.validator_combo.setMinimumWidth(200)
        self.validator_combo.lineEdit().setPlaceholderText("Choisir ou saisir un nom…")
        self._populate_validators()
        validator_bar.addWidget(self.validator_combo)
        validator_bar.addStretch()
        root.addLayout(validator_bar)

        # Actions
        action_bar = QHBoxLayout()
        self.btn_validate = QPushButton("✓  Valider la sélection")
        self.btn_validate.setStyleSheet(
            "QPushButton{background:#2e7d32;color:white;font-weight:bold;padding:6px 16px;}"
            "QPushButton:hover{background:#388e3c;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self.btn_reject = QPushButton("✗  Rejeter la sélection")
        self.btn_reject.setStyleSheet(
            "QPushButton{background:#c62828;color:white;font-weight:bold;padding:6px 16px;}"
            "QPushButton:hover{background:#d32f2f;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self.btn_validate.setEnabled(False)
        self.btn_reject.setEnabled(False)
        self.btn_validate.clicked.connect(self._on_validate)
        self.btn_reject.clicked.connect(self._on_reject)
        action_bar.addWidget(self.btn_validate)
        action_bar.addWidget(self.btn_reject)
        action_bar.addStretch()
        if self._show_close:
            btn_close = QPushButton("Fermer")
            btn_close.clicked.connect(self.close)
            action_bar.addWidget(btn_close)
        root.addLayout(action_bar)

    def _refresh_legend(self) -> None:
        while self.legend_bar.count():
            item = self.legend_bar.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        show_all = self.status_combo.currentData() == "all" if hasattr(self, "status_combo") else False
        legend_items = [
            ("Draft sans source", _COLOR_WARN),
            ("Draft avec source", _COLOR_OK),
        ]
        if show_all:
            legend_items += [
                ("Validé", _COLOR_VALIDATED),
                ("Déprécié", _COLOR_DEPRECATED),
            ]
        for label, color in legend_items:
            lbl = QLabel(f"  ■ {label}  ")
            lbl.setStyleSheet(
                f"background:{color.name()}; color:black; border-radius:3px; padding:2px 6px;"
            )
            self.legend_bar.addWidget(lbl)
        self.legend_bar.addStretch()

    def _populate_validators(self) -> None:
        self.validator_combo.clear()
        try:
            conn = sqlite3.connect(self.sqlite_path)
            rows = conn.execute(
                "SELECT id, name FROM contributors ORDER BY name"
            ).fetchall()
            conn.close()
            for row_id, name in rows:
                self.validator_combo.addItem(name, row_id)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Chargement
    # ------------------------------------------------------------------

    def _where_clause(self, alias: str) -> str:
        """Retourne la clause WHERE selon le filtre statut sélectionné."""
        if self.status_combo.currentData() == "draft":
            return f"WHERE {alias}.status = 'draft'"
        return ""

    def _load_table(self) -> None:
        self._refresh_legend()
        selected_key = self.table_combo.currentData()
        try:
            self.table_widget.itemChanged.disconnect()
        except RuntimeError:
            pass

        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row

        if selected_key == "all":
            self._load_all(conn)
        else:
            self._load_single(conn, selected_key)

        conn.close()
        self.table_widget.itemChanged.connect(self._on_item_changed)
        self._filter_rows(self.search_edit.text())
        self._update_sel_count()

    def _load_all(self, conn: sqlite3.Connection) -> None:
        """Vue unifiée : colonnes fixes Statut / Nom / Source / Contributeur / Créé le."""
        rows_all: list[tuple] = []
        for key, meta in TABLES_META.items():
            alias = meta["alias"]
            where = self._where_clause(alias)
            query = meta["summary_tpl"].format(where=where)
            for row in conn.execute(query).fetchall():
                d = dict(row)
                row_id = d.pop("id")
                vals = [d.get(h, "") for h in _SUMMARY_HEADERS]
                rows_all.append((key, row_id, vals))

        display_headers = ["Table"] + _SUMMARY_HEADERS
        self._fill_widget(rows_all, display_headers, show_table_col=True)
        self.count_label.setText(f"{len(rows_all)} entrée(s)")

    def _load_single(self, conn: sqlite3.Connection, key: str) -> None:
        meta = TABLES_META[key]
        alias = meta["alias"]
        where = self._where_clause(alias)
        query = meta["query_tpl"].format(where=where)
        rows_all = []
        headers = []
        for row in conn.execute(query).fetchall():
            d = dict(row)
            row_id = d.pop("id")
            if not headers:
                headers = list(d.keys())
            rows_all.append((key, row_id, list(d.values())))

        self._fill_widget(rows_all, headers, show_table_col=False)
        self.count_label.setText(f"{len(rows_all)} entrée(s)")

    def _filter_rows(self, text: str = "") -> None:
        """Masque les lignes ne contenant pas le texte cherché."""
        needle = text.strip().lower()
        total = self.table_widget.rowCount()
        visible = 0
        for r in range(total):
            if not needle:
                self.table_widget.setRowHidden(r, False)
                visible += 1
            else:
                match = any(
                    (item := self.table_widget.item(r, c)) is not None
                    and needle in item.text().lower()
                    for c in range(self.table_widget.columnCount())
                )
                self.table_widget.setRowHidden(r, not match)
                if match:
                    visible += 1
        if needle:
            self.count_label.setText(f"{visible}/{total} entrée(s)")
        else:
            self.count_label.setText(f"{total} entrée(s)")

    def _fill_widget(
        self,
        rows_all: list[tuple],
        display_headers: list[str],
        show_table_col: bool,
    ) -> None:
        self.table_widget.blockSignals(True)
        self.table_widget.clearContents()
        self.table_widget.setRowCount(len(rows_all))
        self.table_widget.setColumnCount(1 + len(display_headers))
        self.table_widget.setHorizontalHeaderLabels([""] + display_headers)
        self.table_widget.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.table_widget.setColumnWidth(0, 28)

        # Index des colonnes "Statut" et "Source" dans les valeurs affichées
        try:
            status_col_idx = display_headers.index("Statut")
        except ValueError:
            status_col_idx = -1
        try:
            src_col_idx = display_headers.index("Source")
        except ValueError:
            src_col_idx = -1

        # Offset pour accéder aux vals[] (les display_headers incluent "Table" si show_table_col)
        val_offset = 1 if show_table_col else 0

        for r, (db_table, row_id, vals) in enumerate(rows_all):
            status_val = ""
            source_val = ""
            if status_col_idx >= 0:
                status_val = str(vals[status_col_idx - val_offset] or "")
            if src_col_idx >= 0:
                source_val = str(vals[src_col_idx - val_offset] or "")
            row_color = _row_color(status_val or "draft", bool(source_val.strip()))

            # Checkbox
            chk = _item("", row_color)
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            chk.setData(Qt.ItemDataRole.UserRole, (db_table, row_id))
            self.table_widget.setItem(r, 0, chk)

            col_offset = 1
            if show_table_col:
                tbl_item = _item(TABLES_META[db_table]["label"], row_color)
                tbl_item.setFont(QFont("", -1, QFont.Weight.Bold))
                self.table_widget.setItem(r, 1, tbl_item)
                col_offset = 2

            for c, val in enumerate(vals):
                self.table_widget.setItem(r, col_offset + c, _item(val, row_color))

        self.table_widget.blockSignals(False)

    # ------------------------------------------------------------------
    # Sélection
    # ------------------------------------------------------------------

    def _check_all(self) -> None:
        self.table_widget.blockSignals(True)
        for r in range(self.table_widget.rowCount()):
            self.table_widget.item(r, 0).setCheckState(Qt.CheckState.Checked)
        self.table_widget.blockSignals(False)
        self._update_sel_count()

    def _uncheck_all(self) -> None:
        self.table_widget.blockSignals(True)
        for r in range(self.table_widget.rowCount()):
            self.table_widget.item(r, 0).setCheckState(Qt.CheckState.Unchecked)
        self.table_widget.blockSignals(False)
        self._update_sel_count()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._update_sel_count()

    def _update_sel_count(self) -> None:
        n = sum(
            1 for r in range(self.table_widget.rowCount())
            if self.table_widget.item(r, 0) and
               self.table_widget.item(r, 0).checkState() == Qt.CheckState.Checked
        )
        self.sel_count_label.setText(f"{n} sélectionné(e)s")
        self.btn_validate.setEnabled(n > 0)
        self.btn_reject.setEnabled(n > 0)

    def _selected_entries(self) -> list[tuple[str, str]]:
        result = []
        for r in range(self.table_widget.rowCount()):
            item = self.table_widget.item(r, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    # ------------------------------------------------------------------
    # Résolution du validateur (existant ou création à la volée)
    # ------------------------------------------------------------------

    def _resolve_validator_id(self) -> str | None:
        text = self.validator_combo.currentText().strip()
        if not text:
            return None

        for i in range(self.validator_combo.count()):
            if self.validator_combo.itemText(i) == text:
                existing_id = self.validator_combo.itemData(i)
                if existing_id:
                    return existing_id

        reply = QMessageBox.question(
            self, "Nouveau validateur",
            f"Le contributeur « {text} » n'existe pas.\nCréer un nouveau contributeur ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return None

        new_id = str(uuid.uuid4())
        try:
            conn = sqlite3.connect(self.sqlite_path)
            conn.execute(
                "INSERT INTO contributors(id, name, created_at, updated_at) VALUES (?,?,?,?)",
                (new_id, text, _now(), _now()),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de créer le contributeur : {e}")
            return None

        self.validator_combo.addItem(text, new_id)
        return new_id

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_validate(self) -> None:
        entries = self._selected_entries()
        if not entries:
            return
        validator_id = self._resolve_validator_id()
        if not validator_id:
            QMessageBox.warning(self, "Validateur manquant",
                                "Renseignez un validateur avant de valider.")
            return
        reply = QMessageBox.question(
            self, "Confirmer la validation",
            f"Valider {len(entries)} entrée(s) sélectionnée(s) ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            conn = sqlite3.connect(self.sqlite_path)
            now = _now()
            for db_table, row_id in entries:
                conn.execute(
                    f"UPDATE {db_table} SET status='validated',"
                    f" validated_by_id=?, validated_at=?, updated_at=? WHERE id=?",
                    (validator_id, now, now, row_id),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de valider : {e}")
            return
        QMessageBox.information(self, "Succès", f"{len(entries)} entrée(s) validée(s).")
        self.validated.emit()
        self._load_table()

    def _on_reject(self) -> None:
        entries = self._selected_entries()
        if not entries:
            return
        reply = QMessageBox.question(
            self, "Confirmer le rejet",
            f"Rejeter (déprécier) {len(entries)} entrée(s) ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            conn = sqlite3.connect(self.sqlite_path)
            now = _now()
            for db_table, row_id in entries:
                conn.execute(
                    f"UPDATE {db_table} SET status='deprecated',"
                    f" deprecated_at=?, updated_at=? WHERE id=?",
                    (now, now, row_id),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de rejeter : {e}")
            return
        QMessageBox.information(self, "Succès", f"{len(entries)} entrée(s) rejetée(s).")
        self._load_table()


class ValidateWindow(QDialog):
    """Fenêtre de validation standalone (enveloppe QDialog autour de ValidateWidget)."""

    validated = Signal()

    def __init__(self, sqlite_path: str | Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Validation des données — LABeCO2")
        self.resize(1100, 680)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._widget = ValidateWidget(sqlite_path, show_close=True, parent=self)
        self._widget.validated.connect(self.validated)
        lay.addWidget(self._widget)
