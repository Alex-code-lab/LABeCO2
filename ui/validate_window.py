# SPDX-License-Identifier: GPL-3.0-or-later
"""Fenêtre de validation des entrées à valider pour le mainteneur LABeCO2."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from ui.validation_details import format_entry_detail
from ui.validation_ops import now_iso as _now, reject_entries, validate_entries
from ui.sqlite_schema import ensure_app_schema
from tools.admin.workflow import (
    blocking_issues,
    check_entries_quality,
    format_issues as format_admin_issues,
)

_BLACK = QColor(0, 0, 0)

_COLOR_WARN      = QColor(255, 243, 180)   # jaune  : entrée à valider sans source
_COLOR_OK        = QColor(210, 240, 210)   # vert   : entrée à valider avec source
_COLOR_VALIDATED = QColor(200, 225, 255)   # bleu   : validé
_COLOR_DEPRECATED = QColor(220, 220, 220)  # gris   : déprécié
_STATUS_LABEL = {
    "pending": "En attente",
    "draft": "À valider",
    "validated": "Validé",
    "deprecated": "Déprécié",
}
_TYPE_LABEL = {
    "solid": "Solide",
    "liquid": "Liquide",
    "material": "Matériau",
    "transport": "Transport",
    "spend": "Achat",
}


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


def _status_label(status: str) -> str:
    return _STATUS_LABEL.get(str(status or ""), str(status or ""))


def _type_label(value: str) -> str:
    return _TYPE_LABEL.get(str(value or ""), str(value or ""))


def _admin_message(
    parent: QWidget,
    title: str,
    text: str,
    informative: str = "",
    details: str = "",
) -> None:
    _admin_dialog(parent, title, text, informative, details, confirm=False)


def _admin_confirm(
    parent: QWidget,
    title: str,
    text: str,
    informative: str = "",
    details: str = "",
) -> bool:
    return _admin_dialog(parent, title, text, informative, details, confirm=True)


def _admin_dialog(
    parent: QWidget,
    title: str,
    text: str,
    informative: str,
    details: str,
    *,
    confirm: bool,
) -> bool:
    """Dialogue non natif : évite les réponses macOS -1002 des QMessageBox détaillées."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setModal(True)
    dialog.setMinimumWidth(620)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(10)

    main = QLabel(text)
    main.setWordWrap(True)
    main_font = main.font()
    main_font.setBold(True)
    main.setFont(main_font)
    layout.addWidget(main)

    if informative:
        info = QLabel(informative)
        info.setWordWrap(True)
        layout.addWidget(info)

    if details:
        detail_box = QTextEdit()
        detail_box.setReadOnly(True)
        detail_box.setPlainText(details)
        detail_box.setMinimumHeight(180)
        detail_box.setMaximumHeight(320)
        layout.addWidget(detail_box)

    selected = {"ok": False}
    buttons = QHBoxLayout()
    buttons.addStretch()

    if confirm:
        no_btn = QPushButton("Non")
        yes_btn = QPushButton("Oui")
        no_btn.clicked.connect(dialog.reject)

        def accept() -> None:
            selected["ok"] = True
            dialog.accept()

        yes_btn.clicked.connect(accept)
        buttons.addWidget(no_btn)
        buttons.addWidget(yes_btn)
        yes_btn.setDefault(True)
    else:
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        buttons.addWidget(ok_btn)
        ok_btn.setDefault(True)

    layout.addLayout(buttons)
    dialog.exec()
    return selected["ok"]


# Les requêtes incluent toujours status AS "Statut" et utilisent {where}.
TABLES_META = {
    "emission_factors": {
        "label": "Facteurs d'émission",
        "alias": "ef",
        "query_tpl": """
            SELECT ef.id, ef.id AS "ID", ef.status AS "Statut",
                   CASE WHEN ef.revision_of_id IS NOT NULL AND ef.revision_of_id != ''
                        THEN 'Modification' ELSE 'Nouvelle entrée' END AS "Nature",
                   ef.name AS "Nom", ef.name_key AS "Clé nom",
                   ef.factor_type AS "Type", ef.code_nacres AS "NACRES",
                   ef.co2_factor AS "CO₂", ef.co2_unit AS "Unité CO₂",
                   ef.uncertainty AS "Incert.", ef.density_g_ml AS "Densité",
                   ef.concentration_mg_ml AS "Concentration",
                   s.title AS "Source", ef.source_id AS "Source ID",
                   c.name AS "Ajouté par", ef.contributor_id AS "Contributeur ID",
                   v.name AS "Validé par", ef.validated_by_id AS "Validateur ID",
                   ef.created_at AS "Créé le", ef.updated_at AS "Mis à jour",
                   ef.validated_at AS "Validé le", ef.deprecated_at AS "Déprécié le",
                   ef.contribution_id AS "Contribution", ef.revision_of_id AS "Révision de"
            FROM emission_factors ef
            LEFT JOIN sources s ON s.id = ef.source_id
            LEFT JOIN contributors c ON c.id = ef.contributor_id
            LEFT JOIN contributors v ON v.id = ef.validated_by_id
            {where}
            ORDER BY ef.name
        """,
        "summary_tpl": """
            SELECT ef.id, ef.status AS "Statut",
                   CASE WHEN ef.revision_of_id IS NOT NULL AND ef.revision_of_id != ''
                        THEN 'Modification' ELSE 'Nouvelle entrée' END AS "Nature",
                   ef.factor_type AS "Type",
                   ef.code_nacres AS "NACRES",
                   ef.name AS "Nom",
                   '' AS "Marque",
                   '' AS "Référence",
                   '' AS "Conditionnement",
                   '' AS "Prix (€)",
                   '' AS "Volume vendu (mL)",
                   '' AS "FE lié",
                   ef.co2_factor AS "CO₂",
                   '' AS "Fournisseur",
                   '' AS "Version catalogue",
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
            SELECT m.id, m.id AS "ID", m.status AS "Statut",
                   CASE WHEN m.revision_of_id IS NOT NULL AND m.revision_of_id != ''
                        THEN 'Modification' ELSE 'Nouvelle entrée' END AS "Nature",
                   m.name AS "Nom", m.name_key AS "Clé nom",
                   ef.name AS "FE matériau", m.emission_factor_id AS "FE ID",
                   ef.co2_factor AS "CO₂", ef.co2_unit AS "Unité CO₂",
                   s.title AS "Source", m.source_id AS "Source ID",
                   c.name AS "Ajouté par", m.contributor_id AS "Contributeur ID",
                   v.name AS "Validé par", m.validated_by_id AS "Validateur ID",
                   m.created_at AS "Créé le", m.updated_at AS "Mis à jour",
                   m.validated_at AS "Validé le", m.deprecated_at AS "Déprécié le",
                   m.contribution_id AS "Contribution", m.revision_of_id AS "Révision de"
            FROM materials m
            LEFT JOIN emission_factors ef ON ef.id = m.emission_factor_id
            LEFT JOIN sources s ON s.id = m.source_id
            LEFT JOIN contributors c ON c.id = m.contributor_id
            LEFT JOIN contributors v ON v.id = m.validated_by_id
            {where}
            ORDER BY m.name
        """,
        "summary_tpl": """
            SELECT m.id, m.status AS "Statut",
                   CASE WHEN m.revision_of_id IS NOT NULL AND m.revision_of_id != ''
                        THEN 'Modification' ELSE 'Nouvelle entrée' END AS "Nature",
                   'material' AS "Type",
                   '' AS "NACRES",
                   m.name AS "Nom",
                   '' AS "Marque",
                   '' AS "Référence",
                   '' AS "Conditionnement",
                   '' AS "Prix (€)",
                   '' AS "Volume vendu (mL)",
                   COALESCE(ef.name, 'À relier') AS "FE lié",
                   ef.co2_factor AS "CO₂",
                   '' AS "Fournisseur",
                   '' AS "Version catalogue",
                   s.title AS "Source", c.name AS "Contributeur", m.created_at AS "Créé le"
            FROM materials m
            LEFT JOIN emission_factors ef ON ef.id = m.emission_factor_id
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
            SELECT cp.id, cp.id AS "ID", cp.status AS "Statut",
                   CASE WHEN cp.revision_of_id IS NOT NULL AND cp.revision_of_id != ''
                        THEN 'Modification' ELSE 'Nouvelle entrée' END AS "Nature",
                   cp.name AS "Nom", cp.brand AS "Marque", cp.reference AS "Référence",
                   cp.code_nacres AS "NACRES", cp.product_type AS "Type",
                   cp.sold_packaging_label AS "Conditionnement",
                   cp.price_sold_packaging AS "Prix (€)",
                   cp.units_per_sold_packaging AS "Nbr cond.",
                   cp.sold_unit_volume_ml AS "Volume vendu (mL)",
                   cp.capacity_volume_ml AS "Capacité (mL)",
                   COALESCE(sc.supplier, ijm.source_catalogue, '') AS "Fournisseur",
                   COALESCE(sc.catalogue_date, ijm.imported_at, '') AS "Version catalogue",
                   cp.note AS "Lien / Note / Remarque",
                   CASE WHEN cp.product_type = 'liquid'
                        THEN COALESCE(ef.name, 'À relier')
                        ELSE ''
                   END AS "FE liquide",
                   cp.emission_factor_id AS "FE liquide ID",
                   ef.co2_factor AS "CO₂ FE",
                   ef.co2_unit AS "Unité FE",
                   (SELECT COUNT(*) FROM product_components pc
                    WHERE pc.product_id = cp.id AND pc.mass_g IS NOT NULL) AS "Composants",
                   cp.ijm_catalogue_id AS "Catalogue IJM",
                   s.title AS "Source", cp.source_id AS "Source ID",
                   c.name AS "Ajouté par", cp.contributor_id AS "Contributeur ID",
                   v.name AS "Validé par", cp.validated_by_id AS "Validateur ID",
                   cp.created_at AS "Créé le", cp.updated_at AS "Mis à jour",
                   cp.validated_at AS "Validé le", cp.deprecated_at AS "Déprécié le",
                   cp.contribution_id AS "Contribution", cp.revision_of_id AS "Révision de"
            FROM commercial_products cp
            LEFT JOIN emission_factors ef ON ef.id = cp.emission_factor_id
            LEFT JOIN sources s ON s.id = cp.source_id
            LEFT JOIN contributors c ON c.id = cp.contributor_id
            LEFT JOIN contributors v ON v.id = cp.validated_by_id
            LEFT JOIN supplier_catalogue sc ON sc.id = cp.supplier_catalogue_id
            LEFT JOIN catalogue_ijm ijm ON ijm.id = cp.ijm_catalogue_id
            {where}
            ORDER BY cp.code_nacres, cp.name
        """,
        "summary_tpl": """
            SELECT cp.id, cp.status AS "Statut",
                   CASE WHEN cp.revision_of_id IS NOT NULL AND cp.revision_of_id != ''
                        THEN 'Modification' ELSE 'Nouvelle entrée' END AS "Nature",
                   cp.product_type AS "Type",
                   cp.code_nacres AS "NACRES",
                   cp.name AS "Nom",
                   cp.brand AS "Marque",
                   cp.reference AS "Référence",
                   cp.sold_packaging_label AS "Conditionnement",
                   cp.price_sold_packaging AS "Prix (€)",
                   cp.sold_unit_volume_ml AS "Volume vendu (mL)",
                   CASE WHEN cp.product_type = 'liquid'
                        THEN COALESCE(ef.name, 'Non lié')
                        ELSE (
                            SELECT CAST(COUNT(*) AS TEXT) || ' composant(s)'
                            FROM product_components pc
                            WHERE pc.product_id = cp.id AND pc.mass_g IS NOT NULL
                        )
                   END AS "FE lié",
                   ef.co2_factor AS "CO₂",
                   COALESCE(sc.supplier, ijm.source_catalogue, '') AS "Fournisseur",
                   COALESCE(sc.catalogue_date, ijm.imported_at, '') AS "Version catalogue",
                   s.title AS "Source", c.name AS "Contributeur", cp.created_at AS "Créé le"
            FROM commercial_products cp
            LEFT JOIN emission_factors ef ON ef.id = cp.emission_factor_id
            LEFT JOIN sources s ON s.id = cp.source_id
            LEFT JOIN contributors c ON c.id = cp.contributor_id
            LEFT JOIN supplier_catalogue sc ON sc.id = cp.supplier_catalogue_id
            LEFT JOIN catalogue_ijm ijm ON ijm.id = cp.ijm_catalogue_id
            {where}
            ORDER BY cp.code_nacres, cp.name
        """,
    },
    "transport_factors": {
        "label": "Facteurs transport",
        "alias": "tf",
        "query_tpl": """
            SELECT tf.id, tf.id AS "ID", tf.status AS "Statut",
                   CASE WHEN tf.revision_of_id IS NOT NULL AND tf.revision_of_id != ''
                        THEN 'Modification' ELSE 'Nouvelle entrée' END AS "Nature",
                   tf.origin AS "Origine", tf.distance_km AS "Distance (km)",
                   tf.mode AS "Mode",
                   tf.factor_kgco2e_per_kg AS "Facteur", tf.uncertainty AS "Incert.",
                   s.title AS "Source", tf.source_id AS "Source ID",
                   c.name AS "Ajouté par", tf.contributor_id AS "Contributeur ID",
                   v.name AS "Validé par", tf.validated_by_id AS "Validateur ID",
                   tf.created_at AS "Créé le", tf.updated_at AS "Mis à jour",
                   tf.validated_at AS "Validé le", tf.deprecated_at AS "Déprécié le",
                   tf.contribution_id AS "Contribution", tf.revision_of_id AS "Révision de"
            FROM transport_factors tf
            LEFT JOIN sources s ON s.id = tf.source_id
            LEFT JOIN contributors c ON c.id = tf.contributor_id
            LEFT JOIN contributors v ON v.id = tf.validated_by_id
            {where}
            ORDER BY tf.origin
        """,
        "summary_tpl": """
            SELECT tf.id, tf.status AS "Statut",
                   CASE WHEN tf.revision_of_id IS NOT NULL AND tf.revision_of_id != ''
                        THEN 'Modification' ELSE 'Nouvelle entrée' END AS "Nature",
                   tf.mode AS "Type",
                   '' AS "NACRES",
                   tf.origin AS "Nom",
                   '' AS "Marque",
                   '' AS "Référence",
                   CASE WHEN tf.distance_km IS NOT NULL THEN CAST(tf.distance_km AS TEXT) || ' km' ELSE '' END AS "Conditionnement",
                   '' AS "Prix (€)",
                   '' AS "Volume vendu (mL)",
                   '' AS "FE lié",
                   tf.factor_kgco2e_per_kg AS "CO₂",
                   '' AS "Fournisseur",
                   '' AS "Version catalogue",
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
_SUMMARY_HEADERS = [
    "Statut",
    "Nature",
    "Type",
    "NACRES",
    "Nom",
    "Marque",
    "Référence",
    "Conditionnement",
    "Prix (€)",
    "Volume vendu (mL)",
    "FE lié",
    "CO₂",
    "Fournisseur",
    "Version catalogue",
    "Source",
    "Contributeur",
    "Créé le",
]


_CP_EDITABLE_FIELDS: dict[str, str] = {
    "Nom":                  "name",
    "Marque":               "brand",
    "Référence":            "reference",
    "NACRES":               "code_nacres",
    "Conditionnement":      "sold_packaging_label",
    "Prix (€)":             "price_sold_packaging",
    "Volume vendu (mL)":    "sold_unit_volume_ml",
    "Capacité (mL)":        "capacity_volume_ml",
    "Nbr cond.":            "units_per_sold_packaging",
    "Lien / Note / Remarque": "note",
}
_CP_NUMERIC_FIELDS = frozenset({
    "price_sold_packaging", "sold_unit_volume_ml",
    "capacity_volume_ml", "units_per_sold_packaging",
})
_CP_ALLOWED_FIELDS = frozenset(_CP_EDITABLE_FIELDS.values())
_COLOR_EDITED = QColor(255, 240, 180)  # jaune clair : modification non sauvegardée


class ValidateWidget(QWidget):
    """Widget de validation embarquable (onglet ou fenêtre standalone)."""

    validated = Signal()
    edit_requested = Signal(str, str)  # (db_table, row_id)

    def __init__(self, sqlite_path: str | Path, show_close: bool = True, parent=None):
        super().__init__(parent)
        self.sqlite_path = Path(sqlite_path)
        self._show_close = show_close
        self._pending_edits: dict[tuple, dict[str, str]] = {}  # (db_table, row_id) → {field: val}
        self._editable_col_to_field: dict[int, str] = {}       # col_index → db_field
        self._build_ui()
        self._load_table()

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # Filtres : deux lignes pour garder des champs lisibles.
        filters = QVBoxLayout()
        filters.setSpacing(6)

        filter_row_main = QHBoxLayout()
        filter_row_main.addWidget(QLabel("Table :"))
        self.table_combo = QComboBox()
        self.table_combo.addItem("Toutes les tables", "all")
        for key, meta in TABLES_META.items():
            self.table_combo.addItem(meta["label"], key)
        self.table_combo.currentIndexChanged.connect(self._load_table)
        self.table_combo.setMinimumWidth(210)
        filter_row_main.addWidget(self.table_combo)

        filter_row_main.addWidget(QLabel("Statut :"))
        self.status_combo = QComboBox()
        self.status_combo.addItem("À valider", "draft")
        self.status_combo.addItem("Tous les statuts", "all")
        self.status_combo.currentIndexChanged.connect(self._load_table)
        self.status_combo.setMinimumWidth(160)
        filter_row_main.addWidget(self.status_combo)

        filter_row_main.addWidget(QLabel("Catégorie :"))
        self.category_combo = QComboBox()
        self.category_combo.addItem("Toutes", "all")
        self.category_combo.addItem("Consommables", "commercial_products")
        self.category_combo.addItem("Facteurs", "emission_factors")
        self.category_combo.addItem("Matériaux", "materials")
        self.category_combo.addItem("Transport", "transport_factors")
        self.category_combo.addItem("Sources", "sources")
        self.category_combo.currentIndexChanged.connect(lambda: self._filter_rows(self.search_edit.text()))
        self.category_combo.setMinimumWidth(180)
        filter_row_main.addWidget(self.category_combo)

        filter_row_main.addWidget(QLabel("Type produit :"))
        self.product_type_combo = QComboBox()
        self.product_type_combo.addItem("Tous", "all")
        self.product_type_combo.addItem("Solides", "solid")
        self.product_type_combo.addItem("Liquides", "liquid")
        self.product_type_combo.currentIndexChanged.connect(lambda: self._filter_rows(self.search_edit.text()))
        self.product_type_combo.setMinimumWidth(130)
        filter_row_main.addWidget(self.product_type_combo)

        filter_row_main.addStretch()
        self.count_label = QLabel("")
        filter_row_main.addWidget(self.count_label)
        filters.addLayout(filter_row_main)

        filter_row_search = QHBoxLayout()
        filter_row_search.addWidget(QLabel("NACRES :"))
        self.nacres_filter_edit = QLineEdit()
        self.nacres_filter_edit.setPlaceholderText("NA25")
        self.nacres_filter_edit.setMinimumWidth(120)
        self.nacres_filter_edit.setMaximumWidth(180)
        self.nacres_filter_edit.textChanged.connect(lambda: self._filter_rows(self.search_edit.text()))
        filter_row_search.addWidget(self.nacres_filter_edit)

        filter_row_search.addWidget(QLabel("Fournisseur :"))
        self.supplier_filter_edit = QLineEdit()
        self.supplier_filter_edit.setPlaceholderText("DUCHEFA")
        self.supplier_filter_edit.setMinimumWidth(180)
        self.supplier_filter_edit.setMaximumWidth(260)
        self.supplier_filter_edit.textChanged.connect(lambda: self._filter_rows(self.search_edit.text()))
        filter_row_search.addWidget(self.supplier_filter_edit)

        filter_row_search.addWidget(QLabel("Recherche :"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filtrer les lignes…")
        self.search_edit.setMinimumWidth(360)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._filter_rows)
        filter_row_search.addWidget(self.search_edit, 1)
        filters.addLayout(filter_row_search)

        root.addLayout(filters)

        # Légende couleurs
        self.legend_bar = QHBoxLayout()
        root.addLayout(self.legend_bar)
        self._refresh_legend()

        # Tableau
        self.table_widget = QTableWidget()
        self.table_widget.setAlternatingRowColors(False)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked)
        self.table_widget.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.setSortingEnabled(True)
        self.table_widget.itemSelectionChanged.connect(self._show_selected_detail)
        root.addWidget(self.table_widget)

        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setMaximumHeight(180)
        self.detail_view.setPlaceholderText("Sélectionnez une ligne pour voir le détail.")
        self.detail_view.setFont(QFont("Courier", 10))
        root.addWidget(self.detail_view)

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

        # Barre de sauvegarde des modifications inline
        save_bar = QHBoxLayout()
        self.btn_save_edits = QPushButton("Sauvegarder les modifications")
        self.btn_save_edits.setStyleSheet(
            "QPushButton{background:#1565c0;color:white;font-weight:bold;padding:6px 16px;}"
            "QPushButton:hover{background:#1976d2;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self.btn_save_edits.setEnabled(False)
        self.btn_save_edits.clicked.connect(self._save_pending_edits)
        save_bar.addWidget(self.btn_save_edits)
        self.pending_edits_label = QLabel("")
        self.pending_edits_label.setStyleSheet("color: #b45309; font-style: italic;")
        save_bar.addWidget(self.pending_edits_label)
        save_bar.addStretch()
        root.addLayout(save_bar)

        # Actions
        action_bar = QHBoxLayout()
        self.btn_validate = QPushButton("Valider la sélection")
        self.btn_validate.setStyleSheet(
            "QPushButton{background:#2e7d32;color:white;font-weight:bold;padding:6px 16px;}"
            "QPushButton:hover{background:#388e3c;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self.btn_reject = QPushButton("Rejeter la sélection")
        self.btn_reject.setStyleSheet(
            "QPushButton{background:#c62828;color:white;font-weight:bold;padding:6px 16px;}"
            "QPushButton:hover{background:#d32f2f;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self.btn_edit = QPushButton("Ouvrir / modifier")
        self.btn_quality = QPushButton("Contrôle qualité sélection")
        self.btn_edit.setStyleSheet(
            "QPushButton{background:#e65100;color:white;font-weight:bold;padding:6px 16px;}"
            "QPushButton:hover{background:#f4511e;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self.btn_validate.setEnabled(False)
        self.btn_reject.setEnabled(False)
        self.btn_edit.setEnabled(False)
        self.btn_quality.setEnabled(False)
        self.btn_validate.clicked.connect(self._on_validate)
        self.btn_reject.clicked.connect(self._on_reject)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_quality.clicked.connect(self._on_quality_check)
        action_bar.addWidget(self.btn_validate)
        action_bar.addWidget(self.btn_reject)
        action_bar.addWidget(self.btn_quality)
        action_bar.addWidget(self.btn_edit)
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
            ("À valider sans source", _COLOR_WARN),
            ("À valider avec source", _COLOR_OK),
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

    def _disconnect_item_changed(self) -> None:
        """Supprime toutes les connexions connues vers _on_item_changed."""
        for _ in range(8):
            try:
                self.table_widget.itemChanged.disconnect(self._on_item_changed)
            except (RuntimeError, TypeError):
                break

    def _connect_item_changed_once(self) -> None:
        self._disconnect_item_changed()
        self.table_widget.itemChanged.connect(self._on_item_changed)

    def _load_table(self) -> None:
        # Avertir si des modifications non sauvegardées vont être perdues
        if self._pending_edits:
            if _admin_confirm(
                self,
                "Modifications non sauvegardées",
                f"{len(self._pending_edits)} produit(s) ont des modifications non sauvegardées.\n"
                "Sauvegarder avant de recharger ?",
            ):
                self._save_pending_edits()
                # _save_pending_edits ne recharge pas la table → on continue
            else:
                self._pending_edits.clear()
                self._update_pending_label()

        self._refresh_legend()
        selected_key = self.table_combo.currentData()
        self._disconnect_item_changed()

        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        ensure_app_schema(conn)

        if selected_key == "all":
            self._load_all(conn)
        else:
            self._load_single(conn, selected_key)

        conn.close()
        self.detail_view.clear()
        self._connect_item_changed_once()
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
        category = self.category_combo.currentData() if hasattr(self, "category_combo") else "all"
        product_type = self.product_type_combo.currentData() if hasattr(self, "product_type_combo") else "all"
        nacres_prefix = self.nacres_filter_edit.text().strip().upper() if hasattr(self, "nacres_filter_edit") else ""
        supplier_filter = self.supplier_filter_edit.text().strip().lower() if hasattr(self, "supplier_filter_edit") else ""
        nacres_col = self._column_index("NACRES")
        type_col = self._column_index("Type")
        supplier_col = self._column_index("Fournisseur")
        total = self.table_widget.rowCount()
        visible = 0
        for r in range(total):
            key_data = self.table_widget.item(r, 0).data(Qt.ItemDataRole.UserRole)
            db_table = key_data[0] if key_data else ""
            row_type = self.table_widget.item(r, type_col).text().strip().lower() if type_col >= 0 and self.table_widget.item(r, type_col) else ""
            row_nacres = self.table_widget.item(r, nacres_col).text().strip().upper() if nacres_col >= 0 and self.table_widget.item(r, nacres_col) else ""
            row_supplier = self.table_widget.item(r, supplier_col).text().strip().lower() if supplier_col >= 0 and self.table_widget.item(r, supplier_col) else ""

            category_match = (
                category in ("", "all")
                or category == db_table
                or (category == "product_solid" and db_table == "commercial_products" and row_type in {"solid", "solide"})
                or (category == "product_liquid" and db_table == "commercial_products" and row_type in {"liquid", "liquide"})
            )
            type_match = (
                product_type in ("", "all")
                or (
                    product_type == "solid"
                    and db_table == "commercial_products"
                    and row_type in {"solid", "solide"}
                )
                or (
                    product_type == "liquid"
                    and db_table == "commercial_products"
                    and row_type in {"liquid", "liquide"}
                )
            )
            nacres_match = not nacres_prefix or row_nacres.startswith(nacres_prefix)
            supplier_match = not supplier_filter or supplier_filter in row_supplier
            text_match = not needle or any(
                (item := self.table_widget.item(r, c)) is not None
                and needle in item.text().lower()
                for c in range(self.table_widget.columnCount())
            )
            match = category_match and type_match and nacres_match and supplier_match and text_match
            self.table_widget.setRowHidden(r, not match)
            if match:
                visible += 1
        has_structured_filter = (
            category not in ("", "all")
            or product_type not in ("", "all")
            or bool(nacres_prefix)
            or bool(supplier_filter)
        )
        if needle or has_structured_filter:
            self.count_label.setText(f"{visible}/{total} entrée(s)")
        else:
            self.count_label.setText(f"{total} entrée(s)")

    def _column_index(self, header: str) -> int:
        for col in range(self.table_widget.columnCount()):
            item = self.table_widget.horizontalHeaderItem(col)
            if item and item.text() == header:
                return col
        return -1

    def _fill_widget(
        self,
        rows_all: list[tuple],
        display_headers: list[str],
        show_table_col: bool,
    ) -> None:
        was_sorting = self.table_widget.isSortingEnabled()
        self.table_widget.blockSignals(True)
        self.table_widget.setSortingEnabled(False)
        try:
            self.table_widget.clearContents()
            self.table_widget.setRowCount(len(rows_all))
            self.table_widget.setColumnCount(1 + len(display_headers))
            self.table_widget.setHorizontalHeaderLabels([""] + display_headers)
            self.table_widget.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Fixed
            )
            self.table_widget.setColumnWidth(0, 28)
            column_widths = (
                ("Type", 95),
                ("NACRES", 80),
                ("Nom", 230),
                ("Marque", 130),
                ("Référence", 110),
                ("Conditionnement", 145),
                ("Prix (€)", 80),
                ("Volume vendu (mL)", 115),
                ("Capacité (mL)", 105),
                ("Nbr cond.", 80),
                ("FE lié", 180),
                ("FE liquide", 180),
                ("FE matériau", 180),
                ("CO₂", 90),
                ("CO₂ FE", 90),
                ("Fournisseur", 115),
                ("Version catalogue", 120),
                ("Source", 180),
                ("Lien / Note / Remarque", 220),
            )
            for header, width in column_widths:
                if header in display_headers:
                    col = 1 + display_headers.index(header)
                    self.table_widget.horizontalHeader().setSectionResizeMode(
                        col, QHeaderView.ResizeMode.Interactive
                    )
                    self.table_widget.setColumnWidth(col, width)

            try:
                status_col_idx = display_headers.index("Statut")
            except ValueError:
                status_col_idx = -1
            try:
                src_col_idx = display_headers.index("Source")
            except ValueError:
                src_col_idx = -1

            val_offset = 1 if show_table_col else 0

            self._editable_col_to_field = {}
            if not show_table_col:
                for i, header in enumerate(display_headers):
                    field = _CP_EDITABLE_FIELDS.get(header)
                    if field:
                        self._editable_col_to_field[1 + i] = field

            for r, (db_table, row_id, vals) in enumerate(rows_all):
                status_val = ""
                source_val = ""
                if status_col_idx >= 0:
                    status_val = str(vals[status_col_idx - val_offset] or "")
                if src_col_idx >= 0:
                    source_val = str(vals[src_col_idx - val_offset] or "")
                row_color = _row_color(status_val or "draft", bool(source_val.strip()))

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
                    header = display_headers[c + val_offset] if show_table_col else display_headers[c]
                    display_value = val
                    if header == "Statut":
                        display_value = _status_label(str(val or ""))
                    elif header == "Type":
                        display_value = _type_label(str(val or ""))
                    cell = _item(display_value, row_color)
                    table_col = col_offset + c
                    if (db_table == "commercial_products"
                            and not show_table_col
                            and table_col in self._editable_col_to_field):
                        cell.setFlags(cell.flags() | Qt.ItemFlag.ItemIsEditable)
                        cell.setToolTip("Double-clic pour modifier")
                    self.table_widget.setItem(r, table_col, cell)
        finally:
            self.table_widget.setSortingEnabled(was_sorting)
            self.table_widget.blockSignals(False)

    # ------------------------------------------------------------------
    # Sélection
    # ------------------------------------------------------------------

    def _check_all(self) -> None:
        self.table_widget.blockSignals(True)
        try:
            for r in range(self.table_widget.rowCount()):
                item = self.table_widget.item(r, 0)
                if item:
                    item.setCheckState(Qt.CheckState.Checked)
        finally:
            self.table_widget.blockSignals(False)
        self._update_sel_count()

    def _uncheck_all(self) -> None:
        self.table_widget.blockSignals(True)
        try:
            for r in range(self.table_widget.rowCount()):
                item = self.table_widget.item(r, 0)
                if item:
                    item.setCheckState(Qt.CheckState.Unchecked)
        finally:
            self.table_widget.blockSignals(False)
        self._update_sel_count()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        col = item.column()
        if col == 0:
            self._update_sel_count()
            return
        field = self._editable_col_to_field.get(col)
        if field is None:
            return
        chk = self.table_widget.item(item.row(), 0)
        if not chk:
            return
        user_data = chk.data(Qt.ItemDataRole.UserRole)
        if not isinstance(user_data, tuple) or len(user_data) < 2:
            return
        db_table, row_id = user_data
        if db_table != "commercial_products":
            return
        key = (db_table, row_id)
        self._pending_edits.setdefault(key, {})[field] = item.text()
        item.setBackground(_COLOR_EDITED)
        self._update_pending_label()

    def _update_pending_label(self) -> None:
        n = len(self._pending_edits)
        if n:
            self.pending_edits_label.setText(f"{n} produit(s) modifié(s) non sauvegardé(s)")
            self.btn_save_edits.setEnabled(True)
        else:
            self.pending_edits_label.setText("")
            self.btn_save_edits.setEnabled(False)

    def _save_pending_edits(self) -> None:
        if not self._pending_edits:
            return
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        try:
            with sqlite3.connect(self.sqlite_path) as conn:
                for (db_table, row_id), changes in self._pending_edits.items():
                    if db_table != "commercial_products":
                        continue
                    clean = {k: v for k, v in changes.items() if k in _CP_ALLOWED_FIELDS}
                    if not clean:
                        continue
                    params: dict = {}
                    for field, val in clean.items():
                        if field in _CP_NUMERIC_FIELDS:
                            try:
                                params[field] = float(val.replace(",", ".")) if val.strip() else None
                            except ValueError:
                                params[field] = None
                        else:
                            params[field] = val or None
                    if not params:
                        continue
                    set_clauses = ", ".join(f"{k} = ?" for k in params)
                    values = list(params.values()) + [now, row_id]
                    conn.execute(
                        f"UPDATE commercial_products SET {set_clauses}, updated_at = ? WHERE id = ?",
                        values,
                    )
        except Exception as e:
            _admin_message(self, "Erreur", f"Impossible de sauvegarder : {e}")
            return
        n = len(self._pending_edits)
        # Réinitialiser les fonds jaunes sans recharger toute la table (évite le freeze)
        self.table_widget.blockSignals(True)
        try:
            for r in range(self.table_widget.rowCount()):
                chk = self.table_widget.item(r, 0)
                if not chk:
                    continue
                data = chk.data(Qt.ItemDataRole.UserRole)
                if not isinstance(data, tuple) or len(data) < 2:
                    continue
                key = (data[0], data[1])
                if key not in self._pending_edits:
                    continue
                orig_bg = chk.background()
                for col in self._editable_col_to_field:
                    cell = self.table_widget.item(r, col)
                    if cell:
                        cell.setBackground(orig_bg)
        finally:
            self.table_widget.blockSignals(False)
        self._pending_edits.clear()
        self._update_pending_label()
        _admin_message(self, "Sauvegardé", f"{n} produit(s) mis à jour.")

    _EDITABLE_TABLES = frozenset({"emission_factors", "materials", "commercial_products"})

    def _update_sel_count(self) -> None:
        checked = [
            self.table_widget.item(r, 0)
            for r in range(self.table_widget.rowCount())
            if self.table_widget.item(r, 0) and
               self.table_widget.item(r, 0).checkState() == Qt.CheckState.Checked
        ]
        n = len(checked)
        self.sel_count_label.setText(f"{n} sélectionné(e)s")
        self.btn_validate.setEnabled(n > 0)
        self.btn_reject.setEnabled(n > 0)
        self.btn_quality.setEnabled(n > 0)
        can_edit = (
            n == 1 and
            checked[0].data(Qt.ItemDataRole.UserRole) is not None and
            checked[0].data(Qt.ItemDataRole.UserRole)[0] in self._EDITABLE_TABLES
        )
        self.btn_edit.setEnabled(can_edit)

    def _selected_entries(self) -> list[tuple[str, str]]:
        result = []
        for r in range(self.table_widget.rowCount()):
            item = self.table_widget.item(r, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    def _quality_issues_for_selection(self) -> list:
        entries = self._selected_entries()
        return self._quality_issues_for_entries(entries)

    def _quality_issues_for_entries(self, entries: list[tuple[str, str]]) -> list:
        if not entries:
            return []
        conn = sqlite3.connect(self.sqlite_path)
        try:
            by_entry = check_entries_quality(conn, entries)
        finally:
            conn.close()
        return [issue for issues in by_entry.values() for issue in issues]

    def _busy_dialog(self, text: str) -> QProgressDialog:
        dialog = QProgressDialog(text, "", 0, 0, self)
        dialog.setCancelButton(None)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setMinimumDuration(0)
        dialog.show()
        QApplication.processEvents()
        return dialog

    def _on_quality_check(self) -> None:
        issues = self._quality_issues_for_selection()
        if not issues:
            _admin_message(self, "Contrôle qualité", "Aucune anomalie détectée sur la sélection.")
            return
        errors = blocking_issues(issues)
        title = "Contrôle qualité - erreurs bloquantes" if errors else "Contrôle qualité - avertissements"
        _admin_message(
            self,
            title,
            f"{len(errors)} erreur(s) bloquante(s), "
            f"{len(issues) - len(errors)} avertissement(s).",
            details=format_admin_issues(issues, max_items=80),
        )

    def _show_selected_detail(self) -> None:
        current_row = self.table_widget.currentRow()
        if current_row < 0:
            self.detail_view.clear()
            return
        item = self.table_widget.item(current_row, 0)
        if not item:
            self.detail_view.clear()
            return
        table, entry_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            conn = sqlite3.connect(self.sqlite_path)
            detail = format_entry_detail(conn, table, entry_id)
            conn.close()
        except Exception as e:
            detail = f"Impossible de charger le détail : {e}"
        self.detail_view.setPlainText(detail)

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

        if not _admin_confirm(
            self,
            "Nouveau validateur",
            f"Le contributeur « {text} » n'existe pas.\nCréer un nouveau contributeur ?",
        ):
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
            _admin_message(self, "Erreur", f"Impossible de créer le contributeur : {e}")
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
        progress = self._busy_dialog(f"Contrôle qualité de {len(entries)} entrée(s)…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            issues = self._quality_issues_for_entries(entries)
        finally:
            QApplication.restoreOverrideCursor()
            progress.close()
        errors = blocking_issues(issues)
        if errors:
            _admin_message(
                self,
                "Validation bloquée",
                "La sélection contient des erreurs qualité bloquantes.",
                "Corrigez ces entrées avant de les valider.",
                format_admin_issues(errors, max_items=80),
            )
            return
        warnings = [issue for issue in issues if issue.severity != "ERROR"]
        if warnings:
            if not _admin_confirm(
                self,
                "Avertissements qualité",
                f"{len(warnings)} avertissement(s) non bloquant(s) sur la sélection.",
                "Valider quand même ces entrées ?",
                format_admin_issues(warnings, max_items=80),
            ):
                return
        validator_id = self._resolve_validator_id()
        if not validator_id:
            _admin_message(self, "Validateur manquant", "Renseignez un validateur avant de valider.")
            return
        if not _admin_confirm(
            self,
            "Confirmer la validation",
            f"Valider {len(entries)} entrée(s) sélectionnée(s) ?",
        ):
            return
        progress = self._busy_dialog(f"Validation de {len(entries)} entrée(s)…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            with sqlite3.connect(self.sqlite_path) as conn:
                validate_entries(conn, entries, validator_id)
                conn.commit()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            progress.close()
            _admin_message(self, "Erreur", f"Impossible de valider : {e}")
            return
        QApplication.restoreOverrideCursor()
        progress.close()
        _admin_message(self, "Succès", f"{len(entries)} entrée(s) validée(s).")
        self.validated.emit()
        self._refresh_after_validate(entries)

    def _refresh_after_validate(self, validated_entries: list[tuple[str, str]]) -> None:
        """Met à jour la table après validation sans recharger tous les widgets (évite le freeze)."""
        self._refresh_after_status_change(validated_entries, "validated")

    def _refresh_after_reject(self, rejected_entries: list[tuple[str, str]]) -> None:
        """Met à jour la table après rejet sans rechargement complet."""
        self._refresh_after_status_change(rejected_entries, "deprecated")

    def _refresh_after_status_change(self, entries: list[tuple[str, str]], new_status: str) -> None:
        changed_set = set(entries)
        status_filter = self.status_combo.currentData()
        keep_in_view = status_filter in ("all", new_status)
        status_col = self._column_index("Statut")
        search_text = self.search_edit.text()
        color = _COLOR_DEPRECATED if new_status == "deprecated" else _COLOR_VALIDATED
        label = _status_label(new_status)

        # Déconnecter itemChanged et couper le tri : modifier "Statut" peut déplacer
        # les lignes si le tableau est trié, ce qui laisse des coches/edits fantômes.
        self._disconnect_item_changed()

        was_sorting = self.table_widget.isSortingEnabled()
        self.table_widget.blockSignals(True)
        self.table_widget.setSortingEnabled(False)
        try:
            self.table_widget.clearSelection()
            rows_to_remove = []
            for r in range(self.table_widget.rowCount()):
                chk = self.table_widget.item(r, 0)
                if not chk:
                    continue
                data = chk.data(Qt.ItemDataRole.UserRole)
                if not isinstance(data, tuple) or len(data) < 2:
                    continue
                entry_key = (data[0], data[1])
                if entry_key not in changed_set:
                    continue
                if keep_in_view:
                    for col in range(self.table_widget.columnCount()):
                        cell = self.table_widget.item(r, col)
                        if cell:
                            cell.setBackground(color)
                            cell.setForeground(_BLACK)
                    if status_col >= 0:
                        s_item = self.table_widget.item(r, status_col)
                        if s_item:
                            s_item.setText(label)
                    chk.setCheckState(Qt.CheckState.Unchecked)
                    chk.setSelected(False)
                else:
                    rows_to_remove.append(r)

            for r in reversed(rows_to_remove):
                self.table_widget.removeRow(r)

            for entry in changed_set:
                self._pending_edits.pop(entry, None)
        finally:
            self.table_widget.setSortingEnabled(was_sorting)
            self.table_widget.blockSignals(False)

        self._connect_item_changed_once()

        self.detail_view.clear()
        self._filter_rows(search_text)
        self._update_pending_label()
        self._update_sel_count()

    def _on_reject(self) -> None:
        entries = self._selected_entries()
        if not entries:
            return
        if not _admin_confirm(
            self,
            "Confirmer le rejet",
            f"Rejeter (déprécier) {len(entries)} entrée(s) ?",
        ):
            return
        progress = self._busy_dialog(f"Dépréciation de {len(entries)} entrée(s)…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            with sqlite3.connect(self.sqlite_path) as conn:
                reject_entries(conn, entries)
                conn.commit()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            progress.close()
            _admin_message(self, "Erreur", f"Impossible de rejeter : {e}")
            return
        QApplication.restoreOverrideCursor()
        progress.close()
        _admin_message(self, "Succès", f"{len(entries)} entrée(s) rejetée(s).")
        self._refresh_after_reject(entries)

    def _on_edit(self) -> None:
        entries = self._selected_entries()
        if len(entries) != 1:
            return
        db_table, row_id = entries[0]
        if db_table not in self._EDITABLE_TABLES:
            return
        self.edit_requested.emit(db_table, row_id)


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
