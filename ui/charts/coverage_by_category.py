# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud.
# windows/graphiques/graph_8_CoverageCategory.py

import numpy as np
import matplotlib
matplotlib.use("QtAgg")

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFileDialog, QToolBar, QStyle, QMessageBox
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, Signal

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from utils.color_utils import CATEGORY_ORDER
from ui.charts.history_utils import iter_history_data


class CoverageCategoryWindow(QDialog):
    """
    Fenêtre affichant la couverture méthodologique du bilan carbone
    par catégorie.

    On distingue :
        - Quantitatif physique (masse réelle)
        - Proxy monétaire (€)
        - Non couvert
    """

    finished = Signal()

    def __init__(self, main_window, parent=None):
        super().__init__(parent)

        self.setAttribute(Qt.WA_DeleteOnClose)
        self.main_window = main_window

        self.setWindowTitle("Couverture méthodologique par catégorie")
        self.setGeometry(300, 200, 900, 600)

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)

        # Toolbar
        toolbar = QToolBar()

        save_icon = self.style().standardIcon(QStyle.SP_DialogSaveButton)
        save_action = QAction(save_icon, "", self)
        save_action.setToolTip("Enregistrer l'image")
        save_action.triggered.connect(self.save_image)
        toolbar.addAction(save_action)

        refresh_icon = self.style().standardIcon(QStyle.SP_BrowserReload)
        refresh_action = QAction(refresh_icon, "", self)
        refresh_action.setToolTip("Actualiser le graphique")
        refresh_action.triggered.connect(self.refresh_data)
        toolbar.addAction(refresh_action)

        layout = QVBoxLayout()
        layout.addWidget(toolbar)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

        self.main_window.data_changed.connect(self.refresh_data)

        self.refresh_data()

    # ==============================================================
    # DATA
    # ==============================================================

    def refresh_data(self):
        """
        Classe les émissions par catégorie selon la méthode utilisée.
        """

        coverage = {
            cat: {"mass": 0.0, "price": 0.0, "none": 0.0}
            for cat in CATEGORY_ORDER
        }

        for data in iter_history_data(self.main_window.history_list):
            category = data.get("category", "")
            if category not in coverage:
                continue

            emission_mass = float(data.get("emission_mass", 0.0) or 0.0)
            emission_price = float(data.get("emissions_price", 0.0) or 0.0)

            if emission_mass > 0:
                coverage[category]["mass"] += emission_mass
            elif emission_price > 0:
                coverage[category]["price"] += emission_price
            else:
                coverage[category]["none"] += 1

        self.coverage = coverage
        self.plot_chart()

    # ==============================================================
    # PLOT
    # ==============================================================

    def plot_chart(self):
        """
        Stacked bar chart de la couverture par catégorie.
        """

        self.figure.clear()
        ax = self.figure.add_subplot(111)

        categories = [cat for cat in CATEGORY_ORDER if cat in self.coverage]

        mass_vals = [self.coverage[cat]["mass"] for cat in categories]
        price_vals = [self.coverage[cat]["price"] for cat in categories]
        none_vals = [self.coverage[cat]["none"] for cat in categories]

        x = np.arange(len(categories))
        width = 0.7

        ax.bar(x, mass_vals, width, label="Quantitatif physique")
        ax.bar(x, price_vals, width, bottom=mass_vals, label="Proxy monétaire")

        bottom_none = [m + p for m, p in zip(mass_vals, price_vals)]
        ax.bar(x, none_vals, width, bottom=bottom_none, label="Non couvert")

        ax.set_xticks(x)
        ax.set_xticklabels(categories, rotation=20, ha="right")

        ax.set_ylabel("Contribution au bilan")
        ax.set_title("Couverture méthodologique du bilan carbone par catégorie")

        ax.legend()

        self.figure.tight_layout()
        self.canvas.draw()

    # ==============================================================
    # SAVE
    # ==============================================================

    def save_image(self):
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Enregistrer l'image",
            "",
            "Images PNG (*.png);;Images JPEG (*.jpg *.jpeg);;Fichiers PDF (*.pdf)"
        )

        if not file_name:
            return

        if not any(file_name.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".pdf"]):
            file_name += ".png"

        try:
            self.figure.savefig(file_name)
            QMessageBox.information(self, "Succès", f"Image enregistrée dans {file_name}")
        except Exception as e:
            QMessageBox.warning(self, "Erreur", str(e))

    # ==============================================================
    # CLOSE
    # ==============================================================

    def closeEvent(self, event):
        self.finished.emit()
        super().closeEvent(event)
