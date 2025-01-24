import numpy as np  # Utilisé pour les calculs numériques (par exemple, les indices x)
import matplotlib.patches  # Peut être utilisé pour ajouter des formes au graphique (non utilisé ici)
from adjustText import adjust_text  # Permet d'éviter le chevauchement des étiquettes dans les graphiques
from PySide6.QtWidgets import (
    QMessageBox, QVBoxLayout, QDialog, QFileDialog, QToolBar, QStyle,
)
from PySide6.QtGui import QAction  # Actions pour la barre d'outils
from PySide6.QtCore import Qt  # Constantes Qt, comme Qt.WA_DeleteOnClose
from matplotlib.figure import Figure  # Représente une figure Matplotlib
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas  # Intègre une figure Matplotlib dans une application Qt
from utils.color_utils import CATEGORY_COLORS, CATEGORY_ORDER, generate_color_shades  # Utilitaires personnalisés pour gérer les couleurs et catégories


class BarChartWindow(QDialog):
    """
    Fenêtre affichant un graphique en barres empilées à 100% 
    représentant la répartition des émissions de CO₂ par sous-catégorie, avec des barres d'erreur.
    """

    def __init__(self, main_window):
        """
        Constructeur de la fenêtre BarChartWindow.

        Paramètres
        ----------
        main_window : MainWindow
            Référence à la fenêtre principale pour accéder aux données et au signal data_changed.
        """
        super().__init__()
        # Assure que la fenêtre est supprimée de la mémoire après sa fermeture
        self.setAttribute(Qt.WA_DeleteOnClose)

        # Configuration initiale de la fenêtre
        self.setWindowTitle("Répartition des émissions de CO₂ par Sous-catégorie")
        self.setGeometry(200, 200, 800, 600)

        # Références et constantes
        self.main_window = main_window  # Référence à la fenêtre principale
        self.category_colors = CATEGORY_COLORS  # Couleurs définies pour chaque catégorie
        self.category_order = CATEGORY_ORDER  # Ordre des catégories

        # Initialisation de l'interface utilisateur
        self.initUI()

        # Chargement initial des données et affichage du graphique
        self.refresh_data()

        # Connecte le signal data_changed à la méthode refresh_data pour mettre à jour le graphique
        self.main_window.data_changed.connect(self.refresh_data)

    def initUI(self):
        """
        Initialise l'interface utilisateur de la fenêtre.
        """
        # Création d'une figure Matplotlib et d'un canvas pour l'affichage
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)

        # Barre d'outils pour les actions utilisateur
        toolbar = QToolBar()

        # Action pour sauvegarder l'image du graphique
        save_icon = self.style().standardIcon(QStyle.SP_DialogSaveButton)
        save_action = QAction(save_icon, "", self)
        save_action.setToolTip("Enregistrer l'image")
        save_action.triggered.connect(self.save_image)  # Connecte l'action à la méthode save_image
        toolbar.addAction(save_action)

        # Action pour rafraîchir le graphique
        refresh_icon = self.style().standardIcon(QStyle.SP_BrowserReload)
        refresh_action = QAction(refresh_icon, "", self)
        refresh_action.setToolTip("Actualiser le graphique")
        refresh_action.triggered.connect(self.refresh_chart)  # Connecte l'action à la méthode refresh_chart
        toolbar.addAction(refresh_action)

        # Organisation des widgets dans un layout vertical
        layout = QVBoxLayout()
        layout.addWidget(toolbar)  # Ajout de la barre d'outils
        layout.addWidget(self.canvas)  # Ajout du canvas
        self.setLayout(layout)

    def refresh_data(self):
        """
        Met à jour les données nécessaires au graphique.
        """
        categories = []  # Liste des catégories
        subcategories = []  # Liste des sous-catégories
        emissions = []  # Liste des émissions
        errors = []  # Liste des erreurs associées

        # Parcourt l'historique des calculs dans la fenêtre principale
        for i in range(self.main_window.history_list.count()):
            item = self.main_window.history_list.item(i)
            data = item.data(Qt.UserRole)  # Récupère les données de l'élément
            if data:
                categories.append(data.get('category', ''))  # Ajoute la catégorie
                subcategories.append(data.get('subcategory', ''))  # Ajoute la sous-catégorie
                emissions.append(data.get('emissions_price', 0))  # Ajoute les émissions
                errors.append(data.get('emissions_price_error', 0))  # Ajoute les erreurs

        # Agrège les émissions par catégorie et sous-catégorie
        subcategory_emissions = {}
        subcategory_errors = {}
        for category, subcat, emission, error in zip(categories, subcategories, emissions, errors):
            if category in self.category_order:  # Vérifie si la catégorie est valide
                if category not in subcategory_emissions:
                    subcategory_emissions[category] = {}
                    subcategory_errors[category] = {}
                # Cumul des émissions et erreurs pour chaque sous-catégorie
                subcategory_emissions[category][subcat] = subcategory_emissions[category].get(subcat, 0) + emission
                subcategory_errors[category][subcat] = (
                    subcategory_errors[category].get(subcat, 0) + error ** 2
                )

        # Convertit les erreurs cumulées en écarts types (somme en quadrature)
        for category in subcategory_errors:
            for subcat in subcategory_errors[category]:
                subcategory_errors[category][subcat] = np.sqrt(subcategory_errors[category][subcat])

        self.subcategory_emissions = subcategory_emissions  # Stocke les résultats
        self.subcategory_errors = subcategory_errors  # Stocke les erreurs
        self.refresh_chart()  # Met à jour le graphique

    def plot_chart(self):
        """
        Trace le graphique en barres empilées à 100% avec des barres d'erreur correctement positionnées.
        Les barres d'erreur sont placées au sommet de chaque segment empilé, et l'axe Y est ajusté automatiquement
        pour inclure toute la plage des barres d'erreur et leurs "caps".
        """
        # Nettoyage de la figure pour éviter les superpositions
        self.figure.clear()

        # Ajout d'un subplot pour le graphique
        bar_ax = self.figure.add_subplot(111)

        # Filtre les catégories présentes dans les données et l'ordre prédéfini
        pie_labels = [cat for cat in self.category_order if cat in self.subcategory_emissions]

        # Indices sur l'axe x pour chaque catégorie
        x_indices = np.arange(len(pie_labels))
        bar_width = 0.8  # Largeur des barres

        # Variable pour suivre la hauteur maximale (y compris les barres d'erreur)
        max_height_with_error = 0
        capsize = 0.05  # Taille des "caps" exprimée comme fraction de l'axe Y

        # Tracé des barres empilées pour chaque catégorie
        for idx, category in enumerate(pie_labels):
            sub_emissions = self.subcategory_emissions[category]  # Récupère les sous-catégories
            sub_errors = self.subcategory_errors[category]
            sub_labels = list(sub_emissions.keys())  # Noms des sous-catégories
            sub_values = list(sub_emissions.values())  # Valeurs des émissions
            sub_err_values = list(sub_errors.values())  # Erreurs des émissions
            total_emission = sum(sub_values)  # Total des émissions pour la catégorie

            # Calcul des proportions pour chaque sous-catégorie
            sub_ratios = [value / total_emission if total_emission != 0 else 0 for value in sub_values]
            sub_error_ratios = [err / total_emission if total_emission != 0 else 0 for err in sub_err_values]

            # Détermine la couleur de base et génère des nuances
            base_color = matplotlib.colors.to_rgb(self.category_colors.get(category, '#cccccc'))
            colors = generate_color_shades(base_color, len(sub_labels))
            bottom = 0  # Position de départ pour empiler les barres

            for i, (ratio, error_ratio) in enumerate(zip(sub_ratios, sub_error_ratios)):
                # Trace une portion de barre pour chaque sous-catégorie
                bar_ax.bar(
                    idx, ratio, bar_width, bottom=bottom, color=colors[i], edgecolor='white'
                )

                # Ajout des barres d'erreur
                # La barre d'erreur est positionnée au sommet de la section empilée (bottom + ratio)
                bar_ax.errorbar(
                    idx, bottom + ratio, yerr=error_ratio,
                    fmt='none', ecolor='black', capsize=5, capthick=1, lw=0.7
                )

                # Met à jour la hauteur maximale avec la barre d'erreur et les caps
                max_height_with_error = max(max_height_with_error, bottom + ratio + error_ratio + capsize)

                # Ajout d'une étiquette sur chaque section
                ypos = bottom + ratio / 2  # Position pour l'étiquette
                label = sub_labels[i]
                if len(label) > 15:  # Tronque les étiquettes trop longues
                    label = label[:11] + '...'
                bar_ax.text(idx, ypos, f"{label}: {ratio * 100:.1f}%", ha='center', va='center', fontsize=6, color='white')
                bottom += ratio  # Met à jour la position pour empiler

            # Ajoute le total sous la barre
            bar_ax.text(idx, -0.1, f"{total_emission:.2f} kg CO₂e", ha='center', va='top', fontsize=8, fontweight='bold')

        # Ajuste dynamiquement l'axe Y pour inclure toutes les barres d'erreur et les "caps"
        y_axis_limit = max_height_with_error + 0.1  # Ajoute une marge dynamique au-dessus
        bar_ax.set_ylim(0, y_axis_limit)

        # Configure l'axe x avec les noms des catégories
        bar_ax.set_xticks(x_indices)
        bar_ax.set_xticklabels(pie_labels, rotation=0, ha='center', fontsize=8, fontweight='bold')

        # Ajoute un titre
        bar_ax.set_title("Répartition des émissions par sous-catégorie avec barres d'erreur", fontsize=12)

        # Supprime les bordures inutiles et l'axe y
        bar_ax.spines['top'].set_visible(False)
        bar_ax.spines['right'].set_visible(False)
        bar_ax.spines['left'].set_visible(False)
        bar_ax.spines['bottom'].set_visible(False)
        bar_ax.yaxis.set_visible(False)

        # Ajuste la mise en page pour éviter les chevauchements
        self.figure.subplots_adjust(top=0.9)

        # Dessine le graphique
        self.canvas.draw()

    def save_image(self):
        """
        Sauvegarde le graphique sous forme d'image.
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
            # Ajoute une extension si nécessaire
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
                # Sauvegarde la figure
                self.figure.savefig(file_name)
                QMessageBox.information(self, 'Succès', f'Image enregistrée avec succès dans {file_name}')
            except Exception as e:
                QMessageBox.warning(self, 'Erreur', f'Erreur lors de l\'enregistrement : {e}')
        else:
            QMessageBox.information(self, 'Annulation', 'Enregistrement annulé.')

    def refresh_chart(self):
        """
        Rafraîchit le graphique en redessinant le canvas.
        """
        self.plot_chart()
        self.canvas.draw_idle()