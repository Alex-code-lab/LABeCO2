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



class PieChartWindow(QDialog):
    """
    Fenêtre d'affichage d'un diagramme en camembert (pie chart) représentant 
    la répartition des émissions de CO₂ par catégorie.

    Cette fenêtre est mise à jour automatiquement lorsqu'une modification 
    des données (ajout, suppression ou modification de calcul) survient 
    dans la fenêtre principale. Elle se connecte donc au signal 
    data_changed émis par la fenêtre MainWindow.

    Elle utilise Matplotlib pour générer un graphique et PyQt5 
    pour l'intégration de ce graphique dans une interface graphique.
    """

    def __init__(self, main_window):
        """
        Constructeur de la fenêtre PieChartWindow.

        Paramètres
        ----------
        main_window : MainWindow
            Une référence à la fenêtre principale, permettant d'accéder 
            à ses données, à l'historique des calculs et au signal data_changed.
        """
        super().__init__()

        # Indique à Qt que la fenêtre doit être supprimée de la mémoire 
        # à sa fermeture, évitant ainsi les références obsolètes.
        self.setAttribute(Qt.WA_DeleteOnClose)

        # Définition du titre et de la taille de la fenêtre
        self.setWindowTitle("Répartition des émissions de CO₂ par catégorie")
        self.setGeometry(150, 150, 800, 600)

        # On conserve une référence à la fenêtre principale 
        # pour accéder aux données et signaux
        self.main_window = main_window

        # Les couleurs et l'ordre des catégories sont définis 
        # par des constantes importées
        self.category_colors = CATEGORY_COLORS
        self.category_order = CATEGORY_ORDER

        # Initialisation de l'interface graphique
        self.initUI()

        # Récupération initiale des données et affichage du graphique
        self.refresh_data()

        # Connecte le signal data_changed de la fenêtre principale 
        # à la méthode refresh_data() pour actualiser le graphique 
        # dès que les données changent.
        self.main_window.data_changed.connect(self.refresh_data)


    def initUI(self):
        """
        Initialise l'interface utilisateur de la fenêtre du camembert.

        Cette méthode :
        - Crée la figure Matplotlib et le canvas pour le dessin du graphique.
        - Ajoute une barre d'outils contenant des actions pour sauvegarder 
          et rafraîchir le graphique.
        - Ajoute le tout dans un layout vertical.
        """
        # Création d'une figure Matplotlib et du canvas associé
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)

        # Création d'une barre d'outils
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

        # Mise en place du layout vertical : barre d'outils + canvas
        layout = QVBoxLayout()
        layout.addWidget(toolbar)
        layout.addWidget(self.canvas)
        self.setLayout(layout)


    def refresh_data(self):
        """
        Met à jour les données pour le graphique en récupérant 
        les calculs présents dans l'historique de la fenêtre principale.

        Cette méthode agrège les émissions de CO₂ par catégorie 
        à partir de l'historique, puis appelle la méthode refresh_chart() 
        pour mettre à jour l'affichage.
        """
        # Listes temporaires pour stocker catégories et émissions
        categories = []
        emissions = []

        # Parcours de l'historique des calculs dans la fenêtre principale
        for i in range(self.main_window.history_list.count()):
            item = self.main_window.history_list.item(i)
            data = item.data(Qt.UserRole)
            if data:
                # On récupère la catégorie et les émissions associées
                categories.append(data.get('category', ''))
                emissions.append(data.get('emissions', 0))

        # Agrégation des émissions par catégorie
        category_emissions = {}
        for category, emission in zip(categories, emissions):
            # On vérifie si la catégorie fait partie de l'ordre défini 
            # dans CATEGORY_ORDER
            if category in self.category_order:
                category_emissions[category] = category_emissions.get(category, 0) + emission

        # Stocke le dictionnaire d'émissions par catégorie
        self.category_emissions = category_emissions

        # Met à jour le graphique (appel de refresh_chart())
        self.refresh_chart()


    def plot_chart(self):
        """
        Dessine le diagramme en camembert dans la figure Matplotlib 
        à partir des données self.category_emissions.

        Cette méthode crée un pie chart affichant la répartition 
        des émissions entre les catégories, avec pourcentage 
        et légende adaptée.
        """
        # Nettoyage de la figure pour un nouveau tracé
        self.figure.clear()

        # Calcul des émissions totales
        total_emission = sum(self.category_emissions.values())

        # Titre du graphique indiquant le total des émissions
        self.figure.suptitle(f"Bilan Carbone : {total_emission:.2f} kg CO₂e", fontsize=16)

        # Détermine les étiquettes (catégories) et les valeurs (émissions) 
        # dans l'ordre prédéfini
        pie_labels = [cat for cat in self.category_order if cat in self.category_emissions]
        pie_values = [self.category_emissions[cat] for cat in pie_labels]

        # Ratios des émissions (pourcentage)
        pie_ratios = [v / total_emission for v in pie_values]

        # Couleurs des parts du camembert
        pie_colors = [matplotlib.colors.to_rgb(self.category_colors.get(cat, '#cccccc')) 
                      for cat in pie_labels]

        # Ajout d'un subplot (un seul graphique)
        pie_ax = self.figure.add_subplot(111)

        # Propriétés du tracé des secteurs (bords blancs, etc.)
        wedge_props = {'linewidth': 0.5, 'edgecolor': 'white'}

        # Création du camembert (pie chart)
        wedges, texts = pie_ax.pie(
            pie_ratios,
            labels=None,          # On gère les étiquettes manuellement plus bas
            startangle=90,        # Démarre à 90° pour orienter le camembert correctement
            colors=pie_colors,
            labeldistance=1.1,    # Distance des étiquettes par rapport au centre
            wedgeprops=wedge_props,
            explode=[0.05]*len(pie_labels)  # Écarte légèrement chaque part
        )

        # Ajout des étiquettes personnalisées avec lignes de connexion
        for i, (wedge, ratio) in enumerate(zip(wedges, pie_ratios)):
            # Calcul de l'angle central du secteur pour positionner l'étiquette
            angle = (wedge.theta2 + wedge.theta1) / 2
            x = np.cos(np.radians(angle))
            y = np.sin(np.radians(angle))

            # Positions des étiquettes (un peu en dehors du cercle)
            label_x = x * 1.2
            label_y = y * 1.2

            # Ligne de connexion entre la part et l'étiquette
            connection_line = matplotlib.patches.ConnectionPatch(
                xyA=(x * 0.95, y * 0.95),
                xyB=(label_x, label_y),
                coordsA='data', coordsB='data',
                axesA=pie_ax, axesB=pie_ax,
                color='gray', lw=0.8
            )
            pie_ax.add_artist(connection_line)

            # Texte de l'étiquette (catégorie + pourcentage)
            label_text = f"{pie_labels[i]}\n{ratio * 100:.1f}%"
            pie_ax.text(
                label_x, label_y,
                label_text,
                ha='center', va='center', fontsize=8,
                bbox=dict(
                    boxstyle="round,pad=0.3", 
                    fc="white", 
                    ec="gray", 
                    lw=0.5
                )
            )

        # On force le graphique à être un cercle parfait (égalisant les axes)
        pie_ax.axis('equal')

        # Couleur de fond du graphique
        pie_ax.set_facecolor('black')

        # Ajustement des marges
        self.figure.tight_layout()

        # Mise à jour de l'affichage sur le canvas
        self.canvas.draw()


    def save_image(self):
        """
        Ouvre une boîte de dialogue pour enregistrer le graphique 
        sous forme d'image (PNG, JPEG, PDF...).

        Cette méthode :
        - Ouvre une boîte de dialogue pour choisir le nom et le format du fichier.
        - Ajoute automatiquement une extension de fichier appropriée si l'utilisateur n'en a pas mis.
        - Enregistre la figure et signale le succès ou l'échec.
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
            # Vérifie l'extension et en ajoute une si besoin
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
                # Avertit en cas d'erreur lors de l'enregistrement
                QMessageBox.warning(self, 'Erreur', f'Erreur lors de l\'enregistrement : {e}')
        else:
            # L'utilisateur a annulé
            QMessageBox.information(self, 'Annulation', 'Enregistrement annulé.')


    def refresh_chart(self):
        """
        Rafraîchit le tracé du graphique en appelant plot_chart(), 
        puis en redessinant le canvas.

        Cette méthode est séparée de refresh_data() pour permettre 
        de re-tracer le graphique sans forcément refaire l'agrégation 
        des données. Elle sera notamment appelée après refresh_data().
        """
        self.plot_chart()
        self.canvas.draw_idle()
