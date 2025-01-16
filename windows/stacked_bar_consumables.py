# windows/stacked_bar_consumables.py

import sys
import math
import pandas as pd
import matplotlib
matplotlib.use('QtAgg')  # ou 'Qt5Agg' selon votre config
import matplotlib.pyplot as plt
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QMessageBox
from PySide6.QtCore import Signal

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

class StackedBarConsumablesWindow(QDialog):
    """
    Fenêtre qui affiche un graphique à barres empilées (stacked bar)
    pour les consommables ayant quantity > 0.
    Elle s'appuie sur l'historique de MainWindow pour récupérer ces données.
    """

    finished = Signal()  # Signal émis quand on ferme la fenêtre

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Barres Empilées - Consommables (Quantité > 0)")

        # On crée la figure matplotlib
        self.fig = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self.fig)

        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)

        # On dessine les données au démarrage
        self.refresh_data()

    def refresh_data(self):
        """
        Récupère les données depuis le parent (MainWindow) et redessine le graphique.
        """
        # Effacer la figure précédente
        self.fig.clear()

        # Vérifier si le parent est un MainWindow
        parent = self.parent()
        if parent is None:
            return

        # On va boucler sur l'historique (QListWidget) de MainWindow
        # et filtrer les items correspondants à la condition :
        #   - category = 'Achats'
        #   - subcategory contient 'Consommables'
        #   - quantity > 0
        # On va préparer des données pour un stacked bar.

        # Par exemple, on peut vouloir représenter :
        #  X = l'intitulé du consommable  (code_nacres / name / etc.)
        #  Y = 2 piles:
        #       - emissions_price (émission calculée "par le prix" dans self.data)
        #       - emission_mass (émission calculée "par la masse" via NACRES)
        #  => On a donc 2 barres empilées par X.

        items_data = []
        for i in range(parent.history_list.count()):
            item = parent.history_list.item(i)
            # Récupérer les données stockées au rôle utilisateur
            data = item.data(Qt.UserRole)  
            if not data:
                continue

            category = data.get('category', '')
            subcat = data.get('subcategory', '')
            quantity = data.get('quantity', 0)
            if category == 'Achats' and 'Consommables' in subcat and quantity > 0:
                emissions_price = data.get('emissions_price', 0.0) or 0.0
                emission_mass = data.get('emission_mass', 0.0) or 0.0
                code_nacres = data.get('code_nacres', 'NA')
                consommable = data.get('consommable', 'NA')

                # On construit un label court
                label = f"{code_nacres} - {consommable}"
                items_data.append((label, emissions_price, emission_mass))

        if not items_data:
            QMessageBox.information(
                self,
                "Aucun consommable",
                "Aucun consommable (Achats + Consommables) avec quantité > 0 n'est présent dans l'historique."
            )
            return

        # items_data = [ (label, emission_price, emission_mass), ... ]
        labels = [d[0] for d in items_data]
        price_values = [d[1] for d in items_data]
        mass_values = [d[2] for d in items_data]

        ax = self.fig.add_subplot(111)
        x_positions = range(len(labels))

        # Création de la première barre (émissions par le prix)
        bar_price = ax.bar(x_positions, price_values, label="Émissions (prix)", color="#1f77b4")

        # Création de la deuxième barre empilée (émissions par la masse)
        bar_mass = ax.bar(x_positions, mass_values, bottom=price_values,
                          label="Émissions (masse)", color="#ff7f0e")

        ax.set_xticks(x_positions)
        ax.set_xticklabels(labels, rotation=45, ha="right")

        ax.set_title("Consommables avec quantité > 0\nÉmissions empilées (prix + masse)")
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