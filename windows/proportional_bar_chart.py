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
    par sous-catégorie, permettant de visualiser la part relative de chaque sous-catégorie 
    au sein de sa catégorie, ainsi que la valeur totale de la catégorie.

    Contrairement au BarChartWindow (barres empilées à 100%), 
    ici les barres ne sont pas normalisées à 100%. 
    La hauteur de chaque barre varie en fonction des émissions totales de la catégorie. 
    Cela permet de comparer non seulement les proportions internes de chaque catégorie, 
    mais aussi l'ampleur globale de leurs émissions respectives.

    Cette fenêtre se met à jour automatiquement via le signal data_changed 
    émis par la fenêtre principale.
    """

    def __init__(self, main_window):
        """
        Constructeur de la fenêtre ProportionalBarChartWindow.

        Paramètres
        ----------
        main_window : MainWindow
            Une référence à la fenêtre principale, permettant d'accéder aux données, 
            à l'historique des calculs, et au signal data_changed.
        """
        super().__init__()

        # Indique à Qt que la fenêtre doit être supprimée de la mémoire à sa fermeture.
        self.setAttribute(Qt.WA_DeleteOnClose)

        # Titre et dimensions de la fenêtre
        self.setWindowTitle("Proportions des émissions de CO₂ par Sous-catégorie")
        self.setGeometry(250, 250, 800, 600)

        # Référence à la fenêtre principale pour récupérer les données et connecter les signaux
        self.main_window = main_window

        # Couleurs et ordre des catégories définis en constantes
        self.category_colors = CATEGORY_COLORS
        self.category_order = CATEGORY_ORDER

        # Initialise l'interface graphique
        self.initUI()

        # Chargement initial des données et affichage du graphique
        self.refresh_data()

        # Connecte le signal data_changed de la fenêtre principale 
        # pour actualiser le graphique dès que les données changent.
        self.main_window.data_changed.connect(self.refresh_data)


    def initUI(self):
        """
        Initialise l'interface utilisateur de la fenêtre de graphique.

        Cette méthode :
        - Crée une figure Matplotlib et un canvas pour afficher le graphique.
        - Ajoute une barre d'outils avec des actions pour sauvegarder et rafraîchir.
        - Dispose le tout dans un layout vertical.
        """
        # Création de la figure Matplotlib et du canvas associé
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)

        # Barre d'outils (toolbar)
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

        Cette méthode :
        - Parcourt l'historique des calculs,
        - Agrège les émissions par catégorie et sous-catégorie,
        - Calcule également le total par catégorie,
        - Stocke le tout dans self.subcategory_emissions et self.total_emissions,
        - Puis appelle refresh_chart() pour mettre à jour l'affichage du graphique.
        """
        categories = []
        subcategories = []
        emissions = []

        # Récupération des informations depuis l'historique
        for i in range(self.main_window.history_list.count()):
            item = self.main_window.history_list.item(i)
            data = item.data(Qt.UserRole)
            if data:
                category = data.get('category', '')
                subcategory = data.get('subcategory', '')
                emission = data.get('emissions', 0)
                categories.append(category)
                subcategories.append(subcategory)
                emissions.append(emission)

        # Agrégation des émissions par catégorie et sous-catégorie
        subcategory_emissions = {}
        total_emissions = {}
        for category, subcat, emission in zip(categories, subcategories, emissions):
            if category in self.category_order:
                if category not in subcategory_emissions:
                    subcategory_emissions[category] = {}
                # Ajout ou cumul des émissions pour la sous-catégorie concernée
                subcategory_emissions[category][subcat] = subcategory_emissions[category].get(subcat, 0) + emission
                # Calcul du total par catégorie
                total_emissions[category] = total_emissions.get(category, 0) + emission

        # Stockage des données agrégées
        self.subcategory_emissions = subcategory_emissions
        self.total_emissions = total_emissions

        # Rafraîchit le graphique après mise à jour des données
        self.refresh_chart()


    def plot_chart(self):
        """
        Trace le graphique à barres proportionnelles.

        Le principe :
        - Chaque catégorie est représentée par une barre dont la hauteur est proportionnelle 
          au total des émissions de cette catégorie (max_total_emission sert d'étalon).
        - Les sous-catégories sont empilées les unes sur les autres, mais sans normaliser à 100%.
          La hauteur totale de la barre reflète donc la valeur absolue des émissions de la catégorie,
          tandis que la répartition interne montre les proportions entre sous-catégories.
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
            sub_labels = list(sub_emissions.keys())
            sub_values = list(sub_emissions.values())

            # Somme des émissions de la catégorie
            total_category_emission = sum(sub_values)

            # height_ratio indique la hauteur totale de la barre 
            # relative au max_total_emission (pour comparer entre catégories)
            height_ratio = total_category_emission / max_total_emission

            # Calcul des ratios internes (proportions de chaque sous-catégorie dans la catégorie)
            sub_ratios = [v / total_category_emission if total_category_emission != 0 else 0 for v in sub_values]

            # Couleur de base de la catégorie
            base_color = matplotlib.colors.to_rgb(self.category_colors.get(category, '#cccccc'))
            # Génération de nuances pour distinguer les sous-catégories
            colors = generate_color_shades(base_color, len(sub_ratios))

            bottom = 0
            # Empilement de chaque sous-catégorie
            for i, ratio in enumerate(sub_ratios):
                # La hauteur de chaque sous-catégorie = ratio * height_ratio
                height = ratio * height_ratio
                label = sub_labels[i]

                # Tronquer les noms trop longs
                if len(label) > 15:
                    label = label[:11] + '...'

                # Dessine la portion de barre
                bar_ax.bar(idx, height, bar_width, bottom=bottom, color=colors[i], edgecolor='white')

                # Position du texte au milieu de la portion empilée
                ypos = bottom + height / 2
                bar_ax.text(idx, ypos, f"{label}: {ratio * 100:.1f}%", 
                            ha='center', va='center', color='white', fontsize=6)

                # Mise à jour de bottom pour la prochaine sous-catégorie
                bottom += height

            # Affiche la valeur totale (en kg CO₂e) au-dessus de la barre
            bar_ax.text(idx, bottom + 0.02, f"{total_category_emission:.2f} kg CO₂e",
                        ha='center', va='bottom', fontsize=8, color='black', fontweight='bold')

        # Configuration de l'axe x
        bar_ax.set_xticks(x_indices)
        bar_ax.set_xticklabels(pie_labels, rotation=0, ha='center', fontsize=8, color='black', fontweight='bold',
                               bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.7))

        # Étiquette de l'axe y (même si on le masque ensuite)
        bar_ax.set_ylabel('Émissions proportionnelles (kg CO₂e)')

        # Titre du graphique
        bar_ax.set_title('Émissions proportionnelles par catégorie', fontsize=15, pad=30)

        # Suppression des bordures inutiles
        bar_ax.spines['top'].set_visible(False)
        bar_ax.spines['right'].set_visible(False)
        bar_ax.spines['left'].set_visible(False)
        bar_ax.spines['bottom'].set_visible(False)
        bar_ax.yaxis.set_visible(False)  # L'axe y n'est pas nécessairement parlant ici

        # Ajustement de la mise en page
        self.figure.tight_layout()

        # Dessin final sur le canvas
        self.canvas.draw()


    def save_image(self):
        """
        Ouvre une boîte de dialogue pour sauvegarder l'image du graphique.

        - L'utilisateur choisit le fichier et le format.
        - Si aucune extension n'est fournie, on en ajoute une automatiquement.
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
            # Ajout d'une extension si nécessaire
            if not any(file_name.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.pdf']):
                file_name += '.png'

            try:
                # Sauvegarde de la figure
                self.figure.savefig(file_name)
                QMessageBox.information(self, 'Succès', f'Image enregistrée avec succès dans {file_name}')
            except Exception as e:
                QMessageBox.warning(self, 'Erreur', f'Erreur lors de l\'enregistrement : {e}')
        else:
            QMessageBox.information(self, 'Annulation', 'Enregistrement annulé.')


    def refresh_chart(self):
        """
        Rafraîchit l'affichage du graphique.

        Appelle plot_chart() pour redessiner le graphique avec les données 
        mises à jour, puis met à jour le canvas. Cela permet de refléter 
        immédiatement les modifications de l'historique ou d'autres actions 
        dans la fenêtre principale.
        """
        self.plot_chart()
        self.canvas.draw_idle()
