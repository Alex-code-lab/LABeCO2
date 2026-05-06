# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# windows/graphiques/graph_6_proportional_bar_chart_mass.py
import numpy as np
import matplotlib
from PySide6.QtWidgets import (
    QMessageBox, QVBoxLayout, QDialog, QFileDialog, QToolBar, QStyle,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from utils.color_utils import generate_color_shades


class ProportionalBarChartNacresWindow(QDialog):
    """
    Fenêtre affichant un graphique à barres proportionnelles (non normalisées à 100%)
    par code NACRES, avec des barres d'erreur reflétant les incertitudes sur les émissions.
    """

    def __init__(self, main_window):
        super().__init__()

        # Configurer la suppression de la fenêtre après fermeture
        self.setAttribute(Qt.WA_DeleteOnClose)

        # Titre et dimensions de la fenêtre
        self.setWindowTitle("Proportions des émissions de CO₂ par Code NACRES avec Barres d'Erreur")
        self.setGeometry(250, 250, 800, 600)

        # Référence à la fenêtre principale
        self.main_window = main_window

        # Initialisation de l'interface graphique
        self.initUI()

        # Chargement initial des données et affichage du graphique
        self.refresh_data()

        # Connexion au signal de mise à jour des données
        self.main_window.data_changed.connect(self.refresh_data)

    def initUI(self):
        """
        Initialise l'interface utilisateur de la fenêtre de graphique.
        """
        # Création de la figure Matplotlib et du canvas associé
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)

        # Barre d'outils
        toolbar = QToolBar()

        # Action pour enregistrer l'image
        save_icon = self.style().standardIcon(QStyle.SP_DialogSaveButton)
        save_action = QAction(save_icon, "Enregistrer", self)
        save_action.setToolTip("Enregistrer l'image")
        save_action.triggered.connect(self.save_image)
        toolbar.addAction(save_action)

        # Action pour rafraîchir le graphique
        refresh_icon = self.style().standardIcon(QStyle.SP_BrowserReload)
        refresh_action = QAction(refresh_icon, "Actualiser", self)
        refresh_action.setToolTip("Actualiser le graphique")
        refresh_action.triggered.connect(self.refresh_chart)
        toolbar.addAction(refresh_action)

        # Organisation du layout
        layout = QVBoxLayout()
        layout.addWidget(toolbar)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

    def refresh_data(self):
        """
        Met à jour les données à partir de l'historique dans la fenêtre principale.
        """
        nacres_codes = []
        emissions = []
        errors = []

        # Extraction des données depuis l'historique
        for i in range(self.main_window.history_list.count()):
            item = self.main_window.history_list.item(i)
            data = item.data(Qt.UserRole)
            if data:
                code_nacres = data.get('code_nacres', 'NA')
                emission = data.get('emission_mass', 0)
                error = data.get('emission_mass_error', 0)
                if code_nacres != 'NA':  # On filtre les codes NACRES valides
                    nacres_codes.append(code_nacres[:4])  # Garde les 4 premiers caractères
                    emissions.append(emission)
                    errors.append(error)

        # Agrégation des données par code NACRES
        aggregated_emissions = {}
        aggregated_errors = {}
        for code, emission, error in zip(nacres_codes, emissions, errors):
            if code not in aggregated_emissions:
                aggregated_emissions[code] = 0
                aggregated_errors[code] = 0
            aggregated_emissions[code] += emission
            aggregated_errors[code] += error ** 2

        # Conversion des erreurs cumulées en écart-types
        for code in aggregated_errors:
            aggregated_errors[code] = np.sqrt(aggregated_errors[code])

        # Stockage des données
        self.aggregated_emissions = aggregated_emissions
        self.aggregated_errors = aggregated_errors

        # Mise à jour du graphique
        self.refresh_chart()

    def plot_chart(self):
        """
        Trace le graphique à barres proportionnelles avec barres d'erreur.
        """
        # Nettoyage de la figure
        self.figure.clear()

        # Ajout d'un subplot
        bar_ax = self.figure.add_subplot(111)

        # Récupère les codes NACRES ayant des données
        nacres_labels = list(self.aggregated_emissions.keys())
        values = list(self.aggregated_emissions.values())
        errors = list(self.aggregated_errors.values())

        # Positions sur l'axe x
        x_indices = np.arange(len(nacres_labels))
        bar_width = 0.9

        # Génération des couleurs
        base_color = matplotlib.colors.to_rgb("#73c2fb")  # Bleu clair
        colors = generate_color_shades(base_color, len(values))

        # Tracé des barres
        bars = bar_ax.bar(x_indices, values, bar_width, color=colors, edgecolor='white')

        # Barres d'erreur
        bar_ax.errorbar(x_indices, values, yerr=errors, fmt='none', ecolor='black', capsize=5, capthick=1, lw=0.7)

        # Étiquettes sur les barres (désactivées, commentées)
        # for idx, bar in enumerate(bars):
        #     bar_height = bar.get_height()
        #     bar_ax.text(
        #         bar.get_x() + bar.get_width() / 2, bar_height / 2,
        #         f"{bar_height:.2f}",
        #         ha='center', va='center', fontsize=8, color='white'
        #     )

        # Configuration de l'axe x
        bar_ax.set_xticks(x_indices)
        bar_ax.set_xticklabels(nacres_labels, rotation=45, ha='right', fontsize=10)

        # Titre
        bar_ax.set_title("Émissions proportionnelles par Code NACRES avec barres d'erreur", fontsize=15, pad=30)

        # Nettoyage des bordures
        bar_ax.spines['top'].set_visible(False)
        bar_ax.spines['right'].set_visible(False)
        bar_ax.spines['left'].set_visible(False)
        bar_ax.spines['bottom'].set_visible(False)
        bar_ax.yaxis.set_visible(False)

        # Ajustement du layout
        self.figure.tight_layout()
        self.canvas.draw()

    def save_image(self):
        """
        Sauvegarde l'image du graphique.
        """
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Enregistrer l'image",
            "",
            "Images PNG (*.png);;Images JPEG (*.jpg *.jpeg);;Fichiers PDF (*.pdf);;Tous les fichiers (*)"
        )
        if file_name:
            try:
                self.figure.savefig(file_name)
                QMessageBox.information(self, 'Succès', f'Image enregistrée avec succès dans {file_name}')
            except Exception as e:
                QMessageBox.warning(self, 'Erreur', f'Erreur lors de l enregistrement : {e}')

    def refresh_chart(self):
        """
        Rafraîchit l'affichage du graphique.
        """
        self.plot_chart()
        self.canvas.draw_idle()

    def closeEvent(self, event):
        """
        Émet le signal finished quand la fenêtre se ferme,
        pour que MainWindow puisse la remettre à None.
        """
        self.main_window.nacres_chart_window = None
        super().closeEvent(event)