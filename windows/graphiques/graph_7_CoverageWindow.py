

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Fenêtre affichant la couverture des données d'émissions :
# - Quantitatif physique fiable
# - Proxy monétaire
# - Non couvert

import numpy as np
import matplotlib
matplotlib.use('QtAgg')

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFileDialog, QToolBar, QStyle, QMessageBox
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas


class CoverageWindow(QDialog):
    """
    Fenêtre affichant la qualité de couverture des émissions :

    - Quantitatif physique fiable (émissions masse > 0)
    - Proxy monétaire (émissions prix > 0 mais masse == 0)
    - Non couvert (aucune émission calculée)
    """

    def __init__(self, main_window):
        super().__init__()

        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Couverture des émissions (qualité des données)")
        self.setGeometry(300, 200, 900, 600)

        self.main_window = main_window

        self.initUI()
        self.refresh_data()

        # Mise à jour automatique si les données changent
        self.main_window.data_changed.connect(self.refresh_data)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def initUI(self):
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)

        toolbar = QToolBar()

        # Sauvegarde image
        save_icon = self.style().standardIcon(QStyle.SP_DialogSaveButton)
        save_action = QAction(save_icon, "", self)
        save_action.setToolTip("Enregistrer l'image")
        save_action.triggered.connect(self.save_image)
        toolbar.addAction(save_action)

        # Refresh
        refresh_icon = self.style().standardIcon(QStyle.SP_BrowserReload)
        refresh_action = QAction(refresh_icon, "", self)
        refresh_action.setToolTip("Actualiser le graphique")
        refresh_action.triggered.connect(self.refresh_chart)
        toolbar.addAction(refresh_action)

        layout = QVBoxLayout()
        layout.addWidget(toolbar)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

    # ------------------------------------------------------------------
    # DATA
    # ------------------------------------------------------------------

    def refresh_data(self):
        """
        Analyse l'historique pour classifier les émissions selon leur qualité.
        """

        quantitative = 0.0
        proxy = 0.0
        uncovered = 0.0

        for i in range(self.main_window.history_list.count()):
            item = self.main_window.history_list.item(i)
            data = item.data(Qt.UserRole)

            if not data:
                continue

            emission_mass = float(data.get("emission_mass", 0.0) or 0.0)
            emission_price = float(data.get("emissions_price", 0.0) or 0.0)

            # Classification scientifique
            if emission_mass > 0:
                quantitative += emission_mass
            elif emission_price > 0:
                proxy += emission_price
            else:
                uncovered += 1  # comptage des entrées non couvertes

        self.coverage_values = {
            "Quantitatif physique": quantitative,
            "Proxy monétaire": proxy,
            "Non couvert": uncovered,
        }

        self.refresh_chart()

    # ------------------------------------------------------------------
    # PLOT
    # ------------------------------------------------------------------

    def plot_chart(self):
        self.figure.clear()

        ax = self.figure.add_subplot(111)

        labels = list(self.coverage_values.keys())
        values = list(self.coverage_values.values())

        total = sum(values) if sum(values) > 0 else 1
        ratios = [v / total for v in values]

        colors = ["#2ca02c", "#ff7f0e", "#d62728"]

        bars = ax.bar(labels, ratios, color=colors)

        # Ajout des pourcentages
        for bar, ratio, raw in zip(bars, ratios, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() / 2,
                f"{ratio*100:.1f}%\n({raw:.2f})",
                ha="center",
                va="center",
                color="white",
                fontsize=10,
                fontweight="bold",
            )

        ax.set_ylim(0, 1)
        ax.set_ylabel("Fraction des émissions totales")
        ax.set_title("Qualité de couverture des émissions")

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        self.figure.tight_layout()
        self.canvas.draw()

    # ------------------------------------------------------------------

    def refresh_chart(self):
        self.plot_chart()
        self.canvas.draw_idle()

    # ------------------------------------------------------------------

    def save_image(self):
        file_name, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Enregistrer l'image",
            "",
            "Images PNG (*.png);;Images JPEG (*.jpg *.jpeg);;Fichiers PDF (*.pdf);;Tous les fichiers (*)",
        )

        if file_name:
            if not any(file_name.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".pdf"]):
                file_name += ".png"

            try:
                self.figure.savefig(file_name)
                QMessageBox.information(self, "Succès", f"Image enregistrée dans {file_name}")
            except Exception as e:
                QMessageBox.warning(self, "Erreur", f"Erreur lors de l'enregistrement : {e}")
        else:
            QMessageBox.information(self, "Annulation", "Enregistrement annulé.")