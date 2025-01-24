import numpy as np
import matplotlib.patches
from adjustText import adjust_text
from PySide6.QtWidgets import (
    QMessageBox, QVBoxLayout, QDialog, QFileDialog, QToolBar, QStyle,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from utils.color_utils import CATEGORY_COLORS, CATEGORY_ORDER, generate_color_shades


class ProportionalBarChartWindow(QDialog):
    """
    Fenêtre affichant un graphique à barres proportionnelles (non normalisées à 100%)
    par sous-catégorie, avec des barres d'erreur reflétant les incertitudes sur les émissions.
    """

    def __init__(self, main_window):
        super().__init__()

        # Indique à Qt que la fenêtre doit être supprimée de la mémoire à sa fermeture.
        self.setAttribute(Qt.WA_DeleteOnClose)

        # Titre et dimensions de la fenêtre
        self.setWindowTitle("Proportions des émissions de CO₂ par Sous-catégorie avec Barres d'Erreur")
        self.setGeometry(250, 250, 800, 600)

        # Référence à la fenêtre principale
        self.main_window = main_window

        # Couleurs et ordre des catégories définis en constantes
        self.category_colors = CATEGORY_COLORS
        self.category_order = CATEGORY_ORDER

        # Initialise l'interface graphique
        self.initUI()

        # Chargement initial des données et affichage du graphique
        self.refresh_data()

        # Connecte le signal data_changed de la fenêtre principale pour actualiser le graphique
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

        # Ajout du toolbar et du canvas dans un layout vertical
        layout = QVBoxLayout()
        layout.addWidget(toolbar)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

    def refresh_data(self):
        """
        Met à jour les données à partir de l'historique dans la fenêtre principale.
        """
        categories = []
        subcategories = []
        emissions = []
        errors = []  # Liste des erreurs associées

        # Récupération des informations depuis l'historique
        for i in range(self.main_window.history_list.count()):
            item = self.main_window.history_list.item(i)
            data = item.data(Qt.UserRole)
            if data:
                category = data.get('category', '')
                subcategory = data.get('subcategory', '')
                emission = data.get('emissions_price', 0)
                error = data.get('emissions_price_error', 0)
                categories.append(category)
                subcategories.append(subcategory)
                emissions.append(emission)
                errors.append(error)

        # Agrégation des émissions par catégorie et sous-catégorie
        subcategory_emissions = {}
        subcategory_errors = {}
        total_emissions = {}
        for category, subcat, emission, error in zip(categories, subcategories, emissions, errors):
            if category in self.category_order:
                if category not in subcategory_emissions:
                    subcategory_emissions[category] = {}
                    subcategory_errors[category] = {}
                # Ajout ou cumul des émissions et erreurs pour la sous-catégorie concernée
                subcategory_emissions[category][subcat] = subcategory_emissions[category].get(subcat, 0) + emission
                subcategory_errors[category][subcat] = (
                    subcategory_errors[category].get(subcat, 0) + error ** 2
                )
                # Calcul du total par catégorie
                total_emissions[category] = total_emissions.get(category, 0) + emission

        # Convertit les erreurs cumulées en écart-types (somme en quadrature)
        for category in subcategory_errors:
            for subcat in subcategory_errors[category]:
                subcategory_errors[category][subcat] = np.sqrt(subcategory_errors[category][subcat])

        # Stockage des données agrégées
        self.subcategory_emissions = subcategory_emissions
        self.subcategory_errors = subcategory_errors
        self.total_emissions = total_emissions

        # Rafraîchit le graphique après mise à jour des données
        self.refresh_chart()

    def plot_chart(self):
        """
        Trace le graphique à barres proportionnelles avec barres d'erreur.
        """
        # Nettoyage de la figure
        self.figure.clear()

        # Ajout d'un subplot
        bar_ax = self.figure.add_subplot(111)

        # Récupère les catégories qui ont des données et qui sont dans l'ordre défini
        pie_labels = [cat for cat in self.category_order if cat in self.subcategory_emissions]

        # Détermine la catégorie avec le plus d'émissions totales (pour l'échelle)
        max_total_emission = max(self.total_emissions.values()) if self.total_emissions else 1

        # Positions sur l'axe x
        x_indices = np.arange(len(pie_labels))
        bar_width = 0.9

        # Pour chaque catégorie, on crée une barre proportionnelle
        for idx, category in enumerate(pie_labels):
            sub_emissions = self.subcategory_emissions[category]
            sub_errors = self.subcategory_errors[category]
            sub_labels = list(sub_emissions.keys())
            sub_values = list(sub_emissions.values())
            sub_err_values = list(sub_errors.values())

            # Somme des émissions de la catégorie
            total_category_emission = sum(sub_values)

            # height_ratio indique la hauteur totale de la barre 
            # relative au max_total_emission (pour comparer entre catégories)
            height_ratio = total_category_emission / max_total_emission

            # Calcul des ratios internes (proportions de chaque sous-catégorie dans la catégorie)
            sub_ratios = [v / total_category_emission if total_category_emission != 0 else 0 for v in sub_values]
            sub_error_ratios = [err / total_category_emission if total_category_emission != 0 else 0 for err in sub_err_values]

            # Couleur de base de la catégorie
            base_color = matplotlib.colors.to_rgb(self.category_colors.get(category, '#cccccc'))
            colors = generate_color_shades(base_color, len(sub_ratios))

            bottom = 0
            # Empilement de chaque sous-catégorie
            for i, (ratio, error_ratio) in enumerate(zip(sub_ratios, sub_error_ratios)):
                # Hauteur de chaque sous-catégorie = ratio * height_ratio
                height = ratio * height_ratio

                # Dessine la portion de barre
                bar_ax.bar(idx, height, bar_width, bottom=bottom, color=colors[i], edgecolor='white')

                # Ajout de la barre d'erreur au sommet du segment
                bar_ax.errorbar(
                    idx, bottom + height, yerr=error_ratio * height_ratio,
                    fmt='none', ecolor='black', capsize=5, capthick=1, lw=0.7
                )

                # Ajoute un texte au milieu de la portion empilée
                ypos = bottom + height / 2
                label = sub_labels[i]
                if len(label) > 15:
                    label = label[:11] + '...'
                bar_ax.text(idx, ypos, f"{label}: {ratio * 100:.1f}%", 
                            ha='center', va='center', color='white', fontsize=6)

                # Mise à jour de bottom pour la prochaine sous-catégorie
                bottom += height

            # Affiche la valeur totale (en kg CO₂e) au-dessus de la barre
            bar_ax.text(idx, bottom + 0.02, f"{total_category_emission:.2f} kg CO₂e",
                        ha='center', va='bottom', fontsize=8, color='black', fontweight='bold')

        # Configuration de l'axe x
        bar_ax.set_xticks(x_indices)
        bar_ax.set_xticklabels(pie_labels, rotation=0, ha='center', fontsize=8, color='black', fontweight='bold')

        # Titre du graphique
        bar_ax.set_title('Émissions proportionnelles par catégorie avec barres d\'erreur', fontsize=15, pad=30)

        # Suppression des bordures inutiles
        bar_ax.spines['top'].set_visible(False)
        bar_ax.spines['right'].set_visible(False)
        bar_ax.spines['left'].set_visible(False)
        bar_ax.spines['bottom'].set_visible(False)
        bar_ax.yaxis.set_visible(False)

        # Ajustement de la mise en page
        self.figure.tight_layout()

        # Dessin final sur le canvas
        self.canvas.draw()

    def save_image(self):
        """
        Ouvre une boîte de dialogue pour sauvegarder l'image du graphique.
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
            if not any(file_name.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.pdf']):
                file_name += '.png'
            try:
                self.figure.savefig(file_name)
                QMessageBox.information(self, 'Succès', f'Image enregistrée avec succès dans {file_name}')
            except Exception as e:
                QMessageBox.warning(self, 'Erreur', f'Erreur lors de l\'enregistrement : {e}')
        else:
            QMessageBox.information(self, 'Annulation', 'Enregistrement annulé.')

    def refresh_chart(self):
        """
        Rafraîchit l'affichage du graphique.
        """
        self.plot_chart()
        self.canvas.draw_idle()