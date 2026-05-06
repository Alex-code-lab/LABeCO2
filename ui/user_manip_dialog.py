# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

class UserManipDialog(QDialog):
    TABLE_HEADERS = (
        "Inclure",
        "Catégorie",
        "Sous-catégorie",
        "Code",
        "Nom",
        "Valeur",
        "Jours",
        "Qté",
        "Consommable",
        "CO₂ prix",
        "CO₂ masse",
    )

    def __init__(self, parent=None, history_items=None):
        super().__init__(parent)
        self.setWindowTitle("Nouvelle Manip Utilisateur")
        self.setMinimumSize(980, 520)

        layout = QVBoxLayout(self)

        # 1) Label d’explication
        explanation_label = QLabel(
            "Sélectionnez les lignes de l'historique qui composeront la nouvelle manip type,\n"
            "puis entrez un nom.\n\n"
            "Vous retrouverez ensuite cette manip dans 'Ajouter une manip type'."
        )
        explanation_label.setWordWrap(True)
        layout.addWidget(explanation_label)

        # 2) Tableau des lignes d'historique à intégrer à la manip type
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(len(self.TABLE_HEADERS))
        self.history_table.setHorizontalHeaderLabels(self.TABLE_HEADERS)
        self.history_table.setRowCount(len(history_items or []))
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setWordWrap(False)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setMinimumHeight(300)
        self.history_table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f3f4f6;
                color: #000000;
                gridline-color: #d1d5db;
            }
            QTableWidget::item {
                color: #000000;
            }
            QHeaderView::section {
                background-color: #e5e7eb;
                color: #000000;
                font-weight: bold;
            }
        """)
        self.history_table.cellClicked.connect(self.toggle_row_inclusion)

        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(8, QHeaderView.Stretch)
        for column, width in {
            0: 64,
            1: 95,
            2: 145,
            3: 70,
            5: 85,
            6: 55,
            7: 60,
            9: 95,
            10: 95,
        }.items():
            self.history_table.setColumnWidth(column, width)
        layout.addWidget(self.history_table)

        for row, history_item in enumerate(history_items or []):
            self.add_history_row(row, history_item)

        # 3) Champ de saisie pour le nom
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nom de la manip...")
        layout.addWidget(self.name_edit)

        # 4) Boutons OK / Annuler
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self
        )
        layout.addWidget(button_box)

        # Connexions
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)

    def get_manip_name(self):
        """Renvoie le nom saisi par l'utilisateur."""
        return self.name_edit.text().strip()

    def get_selected_history_data(self):
        """Renvoie les données des lignes d'historique cochées, dans l'ordre affiché."""
        selected_data = []
        for row in range(self.history_table.rowCount()):
            include_item = self.history_table.item(row, 0)
            if include_item and include_item.checkState() == Qt.Checked:
                data = include_item.data(Qt.UserRole)
                if data:
                    selected_data.append(data)
        return selected_data

    def add_history_row(self, row, history_item):
        """Ajoute une ligne d'historique formatée dans le tableau."""
        data = history_item.get("data") or {}
        full_text = history_item.get("text", "")

        include_item = QTableWidgetItem()
        include_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        include_item.setCheckState(Qt.Checked if history_item.get("selected", False) else Qt.Unchecked)
        include_item.setData(Qt.UserRole, data)
        include_item.setForeground(QColor("#000000"))
        include_item.setTextAlignment(Qt.AlignCenter)
        include_item.setToolTip("Cocher pour inclure cette ligne dans la manip type.")
        self.history_table.setItem(row, 0, include_item)

        values = (
            data.get("category", ""),
            data.get("subcategory", ""),
            data.get("code_nacres", ""),
            data.get("name", ""),
            self.format_value(data),
            self.format_number(data.get("days", ""), 0),
            self.format_number(data.get("quantity", ""), 2),
            data.get("consommable", ""),
            self.format_emission(data.get("emissions_price", 0.0), data.get("emissions_price_error", 0.0)),
            self.format_mass_emission(data),
        )
        for col, value in enumerate(values, start=1):
            item = self.make_table_item(value, full_text)
            self.history_table.setItem(row, col, item)

    def toggle_row_inclusion(self, row, column):
        """Permet de cocher/décocher une ligne en cliquant n'importe où sur la ligne."""
        if column == 0:
            return

        include_item = self.history_table.item(row, 0)
        if include_item is None:
            return

        next_state = Qt.Unchecked if include_item.checkState() == Qt.Checked else Qt.Checked
        include_item.setCheckState(next_state)

    @staticmethod
    def make_table_item(value, tooltip=""):
        item = QTableWidgetItem(str(value or ""))
        item.setFlags(Qt.ItemIsEnabled)
        item.setForeground(QColor("#000000"))
        item.setToolTip(tooltip or str(value or ""))
        return item

    @staticmethod
    def format_number(value, decimals):
        if value in (None, ""):
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if number != number:
            return ""
        formatted = f"{number:.{decimals}f}"
        return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted

    def format_value(self, data):
        value = self.format_number(data.get("value", ""), 2)
        unit = str(data.get("unit", "") or "")
        return f"{value} {unit}".strip()

    def format_emission(self, value, error):
        value_text = self.format_number(value, 4)
        try:
            error_number = float(error or 0.0)
        except (TypeError, ValueError):
            error_number = 0.0
        if error_number > 0:
            return f"{value_text} ± {self.format_number(error_number, 4)}"
        return value_text

    def format_mass_emission(self, data):
        try:
            emission_mass = float(data.get("emission_mass", 0.0) or 0.0)
            total_mass = float(data.get("total_mass", 0.0) or 0.0)
        except (TypeError, ValueError):
            return "/"

        if emission_mass == 0.0 and total_mass == 0.0:
            return "/"

        return self.format_emission(emission_mass, data.get("emission_mass_error", 0.0))

    def validate_and_accept(self):
        """Valide la sélection et le nom avant de fermer le dialogue."""
        if not self.get_selected_history_data():
            QMessageBox.warning(
                self,
                "Aucune ligne sélectionnée",
                "Sélectionnez au moins une ligne de l'historique pour créer la manip type."
            )
            return

        if not self.get_manip_name():
            QMessageBox.warning(
                self,
                "Nom manquant",
                "Entrez un nom pour la manip type."
            )
            return

        self.accept()
