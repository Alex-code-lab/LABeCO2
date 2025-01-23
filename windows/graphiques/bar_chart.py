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

class BarChartWindow(QDialog):
    """
    Fenêtre affichant un graphique en barres empilées à 100% 
    représentant la répartition des émissions de CO₂ par sous-catégorie.

    Ce graphique permet de visualiser, pour chaque catégorie, la part relative 
    des différentes sous-catégories dans les émissions totales. Les barres 
    sont toutes normalisées à 100%, permettant ainsi une comparaison visuelle 
    facile des proportions entre catégories, indépendamment de leur volume total.

    La fenêtre se met à jour automatiquement lorsque le signal data_changed 
    est émis par la fenêtre principale, reflétant instantanément 
    les dernières modifications de données.
    """

    def __init__(self, main_window):
        """
        Constructeur de la fenêtre BarChartWindow.

        Paramètres
        ----------
        main_window : MainWindow
            Une référence à la fenêtre principale, 
            permettant d'accéder à l'historique des calculs, 
            aux données, et au signal data_changed.
        """
        super().__init__()

        # Indique à Qt que la fenêtre doit être supprimée de la mémoire 
        # lorsqu'elle est fermée, évitant ainsi les références obsolètes.
        self.setAttribute(Qt.WA_DeleteOnClose)

        # Définition du titre et de la géométrie de la fenêtre
        self.setWindowTitle("Répartition des émissions de CO₂ par Sous-catégorie")
        self.setGeometry(200, 200, 800, 600)

        # Référence à la fenêtre principale
        self.main_window = main_window

        # Les couleurs et l'ordre des catégories sont définis dans des constantes
        self.category_colors = CATEGORY_COLORS
        self.category_order = CATEGORY_ORDER

        # Initialise l'interface graphique
        self.initUI()

        # Récupération initiale des données et affichage du graphique
        self.refresh_data()

        # Connexion du signal data_changed du MainWindow 
        # à la méthode refresh_data() pour actualiser le graphique.
        self.main_window.data_changed.connect(self.refresh_data)


    def initUI(self):
        """
        Initialise l'interface utilisateur de la fenêtre du graphique en barres.

        Cette méthode :
        - Crée la figure Matplotlib et le canvas pour l'affichage du graphique.
        - Ajoute une barre d'outils avec des actions pour sauvegarder et rafraîchir le graphique.
        - Dispose le tout dans un layout vertical.
        """
        # Création d'une figure Matplotlib et du canvas associé
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)

        # Création de la barre d'outils
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

        # Ajout du toolbar et du canvas dans un layout vertical
        layout = QVBoxLayout()
        layout.addWidget(toolbar)
        layout.addWidget(self.canvas)
        self.setLayout(layout)


    def refresh_data(self):
        """
        Met à jour les données nécessaires au tracé du graphique 
        en se basant sur l'historique des calculs dans la fenêtre principale.

        Cette méthode :
        - Parcourt l'historique, 
        - Agrège les émissions par catégorie et sous-catégorie,
        - Stocke ces informations dans self.subcategory_emissions,
        - Puis appelle refresh_chart() pour mettre à jour l'affichage.
        """
        categories = []
        subcategories = []
        emissions = []

        # Parcours de l'historique des calculs pour extraire catégories, sous-catégories et émissions
        for i in range(self.main_window.history_list.count()):
            item = self.main_window.history_list.item(i)
            data = item.data(Qt.UserRole)
            if data:
                categories.append(data.get('category', ''))
                subcategories.append(data.get('subcategory', ''))
                emissions.append(data.get('emissions_price', 0))

        # Agrégation des émissions par catégorie et sous-catégorie
        subcategory_emissions = {}
        for category, subcat, emission in zip(categories, subcategories, emissions):
            # On vérifie si la catégorie fait partie de l'ordre prédéfini
            if category in self.category_order:
                if category not in subcategory_emissions:
                    subcategory_emissions[category] = {}
                # Ajoute ou cumule les émissions pour la sous-catégorie concernée
                subcategory_emissions[category][subcat] = subcategory_emissions[category].get(subcat, 0) + emission

        self.subcategory_emissions = subcategory_emissions

        # Met à jour le graphique
        self.refresh_chart()


    def plot_chart(self):
        """
        Trace le graphique en barres empilées à 100%.

        Pour chaque catégorie, on cumule les émissions de ses sous-catégories 
        et on les représente en pourcentage (ratio). Cela permet de voir la part 
        relative de chaque sous-catégorie dans le total de la catégorie, 
        tous les graphiques étant normalisés à 100%.
        """
        # Nettoyage de la figure
        self.figure.clear()

        # Ajout d'un subplot pour le graphique
        bar_ax = self.figure.add_subplot(111)

        # On récupère les catégories présentes dans l'ordre prédéfini 
        # et qui ont des émissions (dans subcategory_emissions).
        pie_labels = [cat for cat in self.category_order if cat in self.subcategory_emissions]

        # Indices sur l'axe x pour chaque catégorie
        x_indices = np.arange(len(pie_labels))
        bar_width = 0.8  # Largeur des barres

        # Pour chaque catégorie, on trace une barre empilée
        for idx, category in enumerate(pie_labels):
            sub_emissions = self.subcategory_emissions[category]
            sub_labels = list(sub_emissions.keys())
            sub_values = list(sub_emissions.values())
            total_emission = sum(sub_values)

            # Calcul des proportions (ratios) de chaque sous-catégorie
            # Si total_emission = 0, on évite la division par zéro 
            # et on met un ratio de 0.
            sub_ratios = [value / total_emission if total_emission != 0 else 0 for value in sub_values]

            # Détermination de la couleur de base pour la catégorie
            base_color = matplotlib.colors.to_rgb(self.category_colors.get(category, '#cccccc'))
            # Génération de nuances de la couleur pour distinguer les sous-catégories
            colors = generate_color_shades(base_color, len(sub_labels))
            bottom = 0  # Position de départ cumulée sur l'axe y pour empiler les barres

            # Tracé de chaque portion de barre (pour chaque sous-catégorie)
            for i, ratio in enumerate(sub_ratios):
                bar_ax.bar(idx, ratio, bar_width, bottom=bottom, color=colors[i], edgecolor='white')
                ypos = bottom + ratio / 2
                label = sub_labels[i]

                # Si le label est trop long, on le tronque
                if len(label) > 15:
                    label = label[:11] + '...'

                # Ajout d'un texte sur la barre, indiquant le label et le pourcentage
                bar_ax.text(idx, ypos, f"{label}: {ratio * 100:.1f}%", 
                            ha='center', va='center', fontsize=6, color='white')
                # Mise à jour de la position "bottom" pour empiler le prochain ratio au-dessus
                bottom += ratio

            # Ajout du total en kg CO₂e sous la barre (en position y négative)
            bar_ax.text(idx, -0.1, f"{total_emission:.2f} kg CO₂e", 
                        ha='center', va='top', fontsize=8, fontweight='bold')

        # Configuration de l'axe x avec les noms des catégories
        bar_ax.set_xticks(x_indices)
        bar_ax.set_xticklabels(pie_labels, rotation=0, ha='center', fontsize=8, fontweight='bold')

        # Ajustement des limites pour un peu d'espace
        bar_ax.set_ylim(0, 1.1)

        # Titre du graphique
        bar_ax.set_title("Répartition des émissions par sous-catégorie", fontsize=12)

        # Suppression des bordures inutiles du graphique
        bar_ax.spines['top'].set_visible(False)
        bar_ax.spines['right'].set_visible(False)
        bar_ax.spines['left'].set_visible(False)
        bar_ax.spines['bottom'].set_visible(False)
        bar_ax.yaxis.set_visible(False)  # On n'a pas besoin de l'axe y visible (tout est en pourcentage)

        # Ajustement de la mise en page
        self.figure.tight_layout()

        # Dessine le graphique sur le canvas
        self.canvas.draw()


    def save_image(self):
        """
        Ouvre une boîte de dialogue pour sauvegarder le graphique sous forme d'image.

        - Permet à l'utilisateur de choisir l'emplacement et le nom du fichier.
        - Ajoute une extension de fichier appropriée si l'utilisateur n'en fournit pas.
        - Affiche un message d'information en cas de succès, ou un avertissement en cas d'erreur.
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
            # Ajout d'une extension de fichier si nécessaire
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
                self.figure.savefig(file_name)
                QMessageBox.information(self, 'Succès', f'Image enregistrée avec succès dans {file_name}')
            except Exception as e:
                # Avertit en cas d'erreur lors de l'enregistrement
                QMessageBox.warning(self, 'Erreur', f'Erreur lors de l\'enregistrement : {e}')
        else:
            # L'utilisateur a annulé l'enregistrement
            QMessageBox.information(self, 'Annulation', 'Enregistrement annulé.')


    def refresh_chart(self):
        """
        Rafraîchit l'affichage du graphique.

        Cette méthode appelle plot_chart() puis redessine le canvas, permettant ainsi de 
        mettre à jour le graphique lorsque les données changent, sans avoir à recharger 
        toutes les données.
        """
        self.plot_chart()
        self.canvas.draw_idle()
