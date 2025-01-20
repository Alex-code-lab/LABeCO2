# windows/stacked_bar_consumables.py

import math
import pandas as pd
import matplotlib
matplotlib.use('QtAgg')  # ou 'Qt5Agg'
import matplotlib.pyplot as plt

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

class StackedBarConsumablesWindow(QDialog):
    """
    Fenêtre qui affiche un graphique de barres côte à côte (grouped bar)
    pour les consommables ayant quantity > 0, groupés par code NACRES.

    - Pour chaque code NACRES, on additionne les émissions par le prix
      et par la masse de tous les consommables correspondants.
    - On dessine 2 barres juxtaposées : "Émissions (prix)" et "Émissions (masse)".
    """

    finished = Signal()  # Émis quand la fenêtre se ferme

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Barres Comparatives - Consommables (Quantité > 0)")

        # Figure Matplotlib
        self.fig = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self.fig)

        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)

        # Dessin initial
        self.refresh_data()

    def refresh_data(self):
        """
        Récupère les données depuis le parent (MainWindow) et redessine le graphique.
        """
        self.fig.clear()

        parent = self.parent()
        if parent is None:
            return

        # On va parcourir l'historique et regrouper (catégorie="Achats", subcat contient "Consommables", quantity>0)
        # par code NACRES. On accumule la somme d'emissions_price et la somme d'emission_mass.
        nacres_data = {}  # dict { code_nacres: {"price": somme, "mass": somme} }

        for i in range(parent.history_list.count()):
            item = parent.history_list.item(i)
            data = item.data(Qt.UserRole)
            if not data:
                continue

            category = data.get('category', '')
            subcat = data.get('subcategory', '')
            quantity = data.get('quantity', 0)
            code_nacres = data.get('code_nacres', 'NA')
            emissions_price = data.get('emissions_price', 0.0) or 0.0
            emission_mass = data.get('emission_mass', 0.0) or 0.0

            # Critère pour retenir la ligne
            if (category == 'Achats'
                and 'Consommables' in subcat
                and quantity > 0
                and code_nacres != 'NA'):
                
                # Initialiser si pas encore présent
                if code_nacres not in nacres_data:
                    nacres_data[code_nacres] = {"price": 0.0, "mass": 0.0}
                
                # Additionner
                nacres_data[code_nacres]["price"] += emissions_price
                nacres_data[code_nacres]["mass"] += emission_mass

        # Vérifier qu'on a des codes NACRES
        if not nacres_data:
            QMessageBox.information(
                self,
                "Aucun consommable",
                "Aucun consommable (Achats + Consommables) avec quantité > 0 n'est présent dans l'historique."
            )
            return

        # Extraire les données pour tracer
        labels = sorted(nacres_data.keys())
        price_values = [nacres_data[c]["price"] for c in labels]
        mass_values = [nacres_data[c]["mass"] for c in labels]

        ax = self.fig.add_subplot(111)

        # Positions sur l'axe X
        x_positions = range(len(labels))
        bar_width = 0.4

        # Barres pour emissions_price
        bar_price = ax.bar(
            [x for x in x_positions],  # positions de base
            price_values,
            width=bar_width,
            label="Émissions (prix)",
            color="#1f77b4"
        )

        # Barres pour emissions_mass, décalées
        bar_mass = ax.bar(
            [x + bar_width for x in x_positions],
            mass_values,
            width=bar_width,
            label="Émissions (masse)",
            color="#ff7f0e"
        )

        # Mettre les labels sur l'axe X
        # On centre les labels au milieu des 2 barres => (x + bar_width/2)
        ax.set_xticks([x + bar_width/2 for x in x_positions])
        ax.set_xticklabels(labels, rotation=45, ha="right")

        ax.set_title("Consommables avec quantité > 0\nComparaison Émissions (prix) vs Émissions (masse)")
        ax.set_ylabel("kg CO₂e")
        ax.legend()

        self.fig.tight_layout()
        self.canvas.draw()

    def closeEvent(self, event):
        """
        Émet un signal quand la fenêtre se ferme,
        pour informer le MainWindow de remettre self.stacked_bar_consumables_window à None.
        """
        self.finished.emit()
        super().closeEvent(event)