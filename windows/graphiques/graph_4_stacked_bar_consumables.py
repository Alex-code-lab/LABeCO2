# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# windows/graphiques/stacked_bar_consumables.py

import math
import pandas as pd
import matplotlib
matplotlib.use('QtAgg')  # ou 'Qt5Agg'
import matplotlib.pyplot as plt

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QMessageBox, QFileDialog, QToolBar, QStyle
)
from PySide6.QtGui import QAction
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

    def __init__(self, main_window, parent=None):
        """
        Constructeur de la fenêtre StackedBarConsumablesWindow.

        Paramètres
        ----------
        main_window : MainWindow
            Référence à la fenêtre principale pour accéder aux données et au signal data_changed.
        parent : QWidget, optional
            Parent Qt, par défaut None.
        """
        super().__init__(parent)
        
        # Assure que la fenêtre est supprimée de la mémoire après sa fermeture
        self.setAttribute(Qt.WA_DeleteOnClose)

        # Configuration de base de la fenêtre
        self.setWindowTitle("Barres Comparatives - Consommables (Quantité > 0)")
        self.setGeometry(200, 200, 800, 600)

        # Référence à la fenêtre principale
        self.main_window = main_window

        # Connexion du signal data_changed au rafraîchissement des données
        self.main_window.data_changed.connect(self.refresh_data)

        # Données agrégées (dictionnaire NACRES)
        self.nacres_data = {}

        # Initialisation de l'IU
        self.initUI()

        # Dessin initial du graphique
        self.refresh_data()

    def initUI(self):
        """
        Initialise l'interface utilisateur :
        - Crée la figure Matplotlib et son canvas
        - Crée la barre d'outils (QToolBar)
        - Ajoute actions de sauvegarde et de rafraîchissement
        - Met le tout dans un layout vertical
        """
        # Création de la figure et du canvas
        self.fig = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self.fig)

        # Barre d'outils
        toolbar = QToolBar()

        # Action pour sauvegarder le graphique
        save_icon = self.style().standardIcon(QStyle.SP_DialogSaveButton)
        save_action = QAction(save_icon, "", self)
        save_action.setToolTip("Enregistrer l'image")
        save_action.triggered.connect(self.save_image)
        toolbar.addAction(save_action)

        # Action pour rafraîchir le graphique
        refresh_icon = self.style().standardIcon(QStyle.SP_BrowserReload)
        refresh_action = QAction(refresh_icon, "", self)
        refresh_action.setToolTip("Actualiser le graphique")
        refresh_action.triggered.connect(self.refresh_chart)
        toolbar.addAction(refresh_action)

        # Organisation des widgets dans un layout vertical
        layout = QVBoxLayout()
        layout.addWidget(toolbar)  # Ajout de la barre d'outils
        layout.addWidget(self.canvas)  # Ajout du canvas
        self.setLayout(layout)

    def refresh_data(self):
        """
        Récupère et agrège les données depuis la fenêtre principale (MainWindow).
        Met à jour self.nacres_data, puis appelle refresh_chart().
        """
        parent = self.main_window
        if parent is None:
            return

        # Réinitialise les données agrégées
        self.nacres_data = {}

        # Parcourt l'historique pour récupérer les consommables
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

            # Critère : Achats -> Consommables, quantity>0, code_nacres != 'NA'
            if (category == 'Achats'
                and 'Consommables' in subcat
                and quantity > 0
                and code_nacres != 'NA'):
                
                if code_nacres not in self.nacres_data:
                    self.nacres_data[code_nacres] = {
                        "price": 0.0,
                        "price_err_sq": 0.0,
                        "mass": 0.0,
                        "mass_err_sq": 0.0
                    }

                self.nacres_data[code_nacres]["price"] += emissions_price
                self.nacres_data[code_nacres]["price_err_sq"] += (emissions_price_error ** 2)

                self.nacres_data[code_nacres]["mass"] += emission_mass
                self.nacres_data[code_nacres]["mass_err_sq"] += (emission_mass_error ** 2)

        # Vérifie s’il y a des données
        if not self.nacres_data:
            QMessageBox.information(
                self,
                "Aucun consommable",
                "Aucun consommable (Achats + Consommables) avec quantité > 0 n'est présent dans l'historique."
            )
            # Efface le graphique si aucune donnée
            self.fig.clear()
            self.canvas.draw()
            return

        # Met à jour l'affichage
        self.refresh_chart()

    def refresh_chart(self):
        """
        Rafraîchit le graphique en appelant plot_chart() et en redessinant le canvas.
        """
        self.plot_chart()
        self.canvas.draw_idle()

    def plot_chart(self):
        """
        Construit le graphique grouped bar (prix vs masse) avec barres d'erreur 
        à partir des données contenues dans self.nacres_data.
        """
        # Efface la figure pour un nouveau tracé
        self.fig.clear()

        # Création du subplot
        ax = self.fig.add_subplot(111)

        # Prépare les listes nécessaires au tracé
        labels = sorted(self.nacres_data.keys())  # Tri alphabétique
        price_values = []
        price_errors = []
        mass_values = []
        mass_errors = []

        for code in labels:
            data = self.nacres_data[code]
            price_sum = data["price"]
            price_err = math.sqrt(data["price_err_sq"])  # Somme en quadrature
            mass_sum = data["mass"]
            mass_err = math.sqrt(data["mass_err_sq"])

            price_values.append(price_sum)
            price_errors.append(price_err)
            mass_values.append(mass_sum)
            mass_errors.append(mass_err)

        # Positions sur l’axe x
        x_positions = range(len(labels))
        bar_width = 0.4

        # Barres pour Émissions (prix)
        bar_price = ax.bar(
            x_positions,
            price_values,
            yerr=price_errors,
            width=bar_width,
            label="Émissions (prix)",
            color="#1f77b4",
            capsize=5
        )

        # Barres pour Émissions (masse), décalées de bar_width
        bar_mass = ax.bar(
            [x + bar_width for x in x_positions],
            mass_values,
            yerr=mass_errors,
            width=bar_width,
            label="Émissions (masse)",
            color="#ff7f0e",
            capsize=5
        )

        # Tronque l’affichage des codes NACRES (ex. 4 premiers caractères)
        truncated_labels = [code[:4] for code in labels]

        # Centre les labels entre les deux barres
        ax.set_xticks([x + bar_width/2 for x in x_positions])
        ax.set_xticklabels(truncated_labels, rotation=45, ha="right")

        # Configuration des titres, légendes, etc.
        ax.set_title("Consommables avec quantité > 0\nComparaison Émissions (prix) vs Émissions (masse)")
        ax.set_ylabel("kg CO₂e")
        ax.legend()

        # Ajustement de la mise en page
        self.fig.tight_layout()

    def save_image(self):
        """
        Ouvre une boîte de dialogue pour sauvegarder le graphique sous forme d'image.
        """
        options = QFileDialog.Options()
        file_name, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Enregistrer l'image",
            "",
            "Images PNG (*.png);;Images JPEG (*.jpg *.jpeg);;Fichiers PDF (*.pdf);;Tous les fichiers (*)",
            options=options
        )
        if file_name:
            # Vérifie si le nom de fichier a bien une extension
            if not any(file_name.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.pdf']):
                if "PNG" in selected_filter:
                    file_name += '.png'
                elif "JPEG" in selected_filter:
                    file_name += '.jpg'
                elif "PDF" in selected_filter:
                    file_name += '.pdf'
                else:
                    file_name += '.png'
            try:
                # Sauvegarde de la figure
                self.fig.savefig(file_name)
                QMessageBox.information(self, 'Succès', f'Image enregistrée avec succès dans {file_name}')
            except Exception as e:
                QMessageBox.warning(self, 'Erreur', f'Erreur lors de l\'enregistrement : {e}')
        else:
            QMessageBox.information(self, 'Annulation', 'Enregistrement annulé.')

    def closeEvent(self, event):
        """
        Émet un signal quand la fenêtre se ferme,
        pour informer le MainWindow de remettre self.stacked_bar_consumables_window à None.
        """
        self.finished.emit()
        super().closeEvent(event)