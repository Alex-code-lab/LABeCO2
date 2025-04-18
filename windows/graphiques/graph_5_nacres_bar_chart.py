# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# windows/graphiques/graph_5_nacres_bar_chart.py
import numpy as np
import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFileDialog, QToolBar, QStyle, QMessageBox
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, Signal
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

# Exemple : si vous avez ce module de couleurs
from utils.color_utils import generate_color_shades


class NacresBarChartWindow(QDialog):
    """
    Fenêtre pour afficher un bar chart basé sur les codes NACRES.
    Chaque barre représente le total des émissions pour un code NACRES,
    avec des barres d'erreur pour refléter les incertitudes associées.
    """

    finished = Signal()  # Émis quand la fenêtre se ferme, pour que MainWindow la remette à None

    def __init__(self, main_window):
        super().__init__(parent=main_window)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self.main_window = main_window
        self.setWindowTitle("Barres NACRES")
        self.setGeometry(300, 200, 800, 600)

        # Création d'une figure Matplotlib
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)

        # Barre d'outils
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

        # Mise en page
        layout = QVBoxLayout()
        layout.addWidget(toolbar)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

        # Chargement initial des données et affichage
        self.refresh_data()

        # Écoute les modifications de données
        self.main_window.data_changed.connect(self.refresh_data)

    def refresh_data(self):
        """
        Récupère l'historique depuis self.main_window.history_list,
        agrège les données par code NACRES, et dessine le graphique.
        """
        self.figure.clear()

        # Récupération des données : 'emissions_price' et erreurs associées
        nacres_dict = {}
        nacres_errors = {}
        for i in range(self.main_window.history_list.count()):
            item = self.main_window.history_list.item(i)
            data = item.data(Qt.UserRole)
            if not data:
                continue

            code_nacres = data.get('code_nacres', 'NA')
            category = data.get('category', '')
            quantity = data.get('quantity', 0)
            emissions_price = data.get('emissions_price', 0.0)
            emissions_error = data.get('emissions_price_error', 0.0)

            # On filtre les données valides
            if code_nacres != 'NA' and category == 'Achats' and quantity > 0:
                code_nacres_short = code_nacres[:4]  # Garde uniquement les 4 premiers caractères
                if code_nacres_short not in nacres_dict:
                    nacres_dict[code_nacres_short] = 0.0
                    nacres_errors[code_nacres_short] = 0.0
                nacres_dict[code_nacres_short] += emissions_price
                nacres_errors[code_nacres_short] += emissions_error ** 2

        # Conversion des erreurs cumulées en écart-types
        for code in nacres_errors:
            nacres_errors[code] = np.sqrt(nacres_errors[code])

        if not nacres_dict:
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, "Aucune donnée NACRES correspondante (Achats + quantity>0).", 
                    ha='center', va='center', transform=ax.transAxes)
            self.canvas.draw()
            return

        # On crée un bar chart
        self.plot_chart(nacres_dict, nacres_errors)

    def plot_chart(self, nacres_dict, nacres_errors):
        """
        Trace le graphique en barres avec barres d'erreur.
        """
        # Préparer les données
        codes = sorted(nacres_dict.keys())
        values = [nacres_dict[c] for c in codes]
        errors = [nacres_errors[c] for c in codes]

        x_indices = np.arange(len(codes))
        bar_width = 0.8

        # Couleur de base
        import matplotlib.colors
        base_color = matplotlib.colors.to_rgb("#73c2fb")  # un bleu clair
        # Génération de nuances si besoin
        color_list = generate_color_shades(base_color, len(values))

        # Création du graphique
        ax = self.figure.add_subplot(111)
        bars = ax.bar(x_indices, values, bar_width, color=color_list, edgecolor='white')

        # Ajout des barres d'erreur
        ax.errorbar(x_indices, values, yerr=errors, fmt='none', ecolor='black', capsize=5, capthick=1, lw=0.7)

        # Affiche la valeur au-dessus de chaque barre (commenté si non nécessaire)
        # for idx, rect in enumerate(bars):
        #     height = rect.get_height()
        #     ax.text(rect.get_x() + rect.get_width()/2, height + 0.01,
        #             f"{height:.2f}", ha='center', va='bottom', fontsize=8)

        # Configuration de l'axe x
        ax.set_xticks(x_indices)
        ax.set_xticklabels(codes, rotation=30, ha='right', fontsize=8)
        ax.set_ylabel("Émissions (kg CO₂e)")
        ax.set_title("Bar Chart par Code NACRES avec Barres d'Erreur")

        # Ajustement du layout
        self.figure.tight_layout()
        self.canvas.draw()

    def save_image(self):
        """
        Ouvre une boîte de dialogue pour sauvegarder l'image du graphique.
        """
        file_name, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Enregistrer l'image",
            "",
            "Images PNG (*.png);;Images JPEG (*.jpg *.jpeg);;Fichiers PDF (*.pdf);;Tous les fichiers (*)"
        )
        if file_name:
            # Ajout d'une extension si nécessaire
            if not any(file_name.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.pdf']):
                file_name += '.png'
            try:
                self.figure.savefig(file_name)
                QMessageBox.information(self, 'Succès', f'Image enregistrée avec succès dans {file_name}')
            except Exception as e:
                QMessageBox.warning(self, 'Erreur', f'Erreur lors de l\'enregistrement : {e}')
        else:
            QMessageBox.information(self, 'Annulation', 'Enregistrement annulé.')

    def closeEvent(self, event):
        """
        Émet le signal finished quand la fenêtre se ferme,
        pour que MainWindow puisse la remettre à None.
        """
        self.finished.emit()
        super().closeEvent(event)