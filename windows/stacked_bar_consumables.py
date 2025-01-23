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

    - Pour chaque code NACRES, on additionne (ou somme en quadrature pour les erreurs)
      les émissions par le prix et par la masse de tous les consommables correspondants.
    - On dessine 2 barres juxtaposées :
      "Émissions (prix)" et "Émissions (masse)", avec leurs barres d'erreur.
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
        Inclut les barres d'erreur pour les émissions (prix et masse).
        """
        self.fig.clear()

        parent = self.parent()
        if parent is None:
            return

        # On va parcourir l'historique et regrouper par code NACRES
        nacres_data = {}  # dict { code_nacres: {"price": somme, "price_err_sq": somme en quadrature, "mass": somme, "mass_err_sq": somme en quadrature } }

        for i in range(parent.history_list.count()):
            item = parent.history_list.item(i)
            data = item.data(Qt.UserRole)
            if not data:
                continue

            category = data.get('category', '')
            subcat = data.get('subcategory', '')
            quantity = data.get('quantity', 0)
            code_nacres = data.get('code_nacres', 'NA')

            # Émissions + erreurs
            emissions_price = float(data.get('emissions_price', 0.0) or 0.0)
            emissions_price_error = float(data.get('emissions_price_error', 0.0) or 0.0)

            emission_mass = float(data.get('emission_mass', 0.0) or 0.0)
            emission_mass_error = float(data.get('emission_mass_error', 0.0) or 0.0)

            # Critère pour retenir la ligne
            if (category == 'Achats'
                and 'Consommables' in subcat
                and quantity > 0
                and code_nacres != 'NA'):
                
                if code_nacres not in nacres_data:
                    nacres_data[code_nacres] = {
                        "price": 0.0,
                        "price_err_sq": 0.0,
                        "mass": 0.0,
                        "mass_err_sq": 0.0
                    }

                nacres_data[code_nacres]["price"] += emissions_price
                nacres_data[code_nacres]["price_err_sq"] += (emissions_price_error ** 2)

                nacres_data[code_nacres]["mass"] += emission_mass
                nacres_data[code_nacres]["mass_err_sq"] += (emission_mass_error ** 2)

        if not nacres_data:
            QMessageBox.information(
                self,
                "Aucun consommable",
                "Aucun consommable (Achats + Consommables) avec quantité > 0 n'est présent dans l'historique."
            )
            return

        # Préparer les listes pour tracer
        labels = sorted(nacres_data.keys())  # tri alpha
        price_values = []
        price_errors = []
        mass_values = []
        mass_errors = []

        for code in labels:
            price_sum = nacres_data[code]["price"]
            price_err = math.sqrt(nacres_data[code]["price_err_sq"])  # somme en quadrature
            mass_sum = nacres_data[code]["mass"]
            mass_err = math.sqrt(nacres_data[code]["mass_err_sq"])

            price_values.append(price_sum)
            price_errors.append(price_err)
            mass_values.append(mass_sum)
            mass_errors.append(mass_err)

        ax = self.fig.add_subplot(111)

        # Positions sur l'axe X
        x_positions = range(len(labels))
        bar_width = 0.4

        # Barres pour emissions_price, avec barres d'erreur
        bar_price = ax.bar(
            x_positions,
            price_values,
            yerr=price_errors,   # barres d'erreur "prix"
            width=bar_width,
            label="Émissions (prix)",
            color="#1f77b4",
            capsize=5  # taille des "caps" pour les barres d'erreur
        )

        # Barres pour emissions_mass, décalées d'un bar_width
        bar_mass = ax.bar(
            [x + bar_width for x in x_positions],
            mass_values,
            yerr=mass_errors,   # barres d'erreur "masse"
            width=bar_width,
            label="Émissions (masse)",
            color="#ff7f0e",
            capsize=5
        )

        # Configurer l'axe X avec des étiquettes tronquées
        # On tronque les labels pour afficher uniquement les 4 premiers caractères
        truncated_labels = [code[:4] for code in labels]

        # On centre les labels entre les deux barres => (x + bar_width/2)
        ax.set_xticks([x + bar_width/2 for x in x_positions])
        ax.set_xticklabels(truncated_labels, rotation=45, ha="right")

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