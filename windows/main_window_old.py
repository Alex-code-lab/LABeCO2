# windows/main_window.py

import sys
import os
import pandas as pd
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QComboBox, QLineEdit,
    QListWidget, QMessageBox, QVBoxLayout, QHBoxLayout, QWidget,
    QInputDialog, QFormLayout, QFileDialog, QDialog, QDialogButtonBox,
    QListWidgetItem, QScrollArea, QSizePolicy, QSpacerItem
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QIntValidator
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from utils.data_loader import load_data, load_logo, resource_path
from windows.pie_chart import PieChartWindow
from windows.bar_chart import BarChartWindow
from windows.proportional_bar_chart import ProportionalBarChartWindow
from windows.data_mass_window import DataMassWindow  # Import de DataMassWindow
from windows.edit_calculation_dialog import EditCalculationDialog  # NOUVEAU IMPORT
from windows.stacked_bar_consumables import StackedBarConsumablesWindow
from windows.nacres_bar_chart import NacresBarChartWindow

class MainWindow(QMainWindow):
    """
    Fenêtre principale de l'application LABeCO₂.

    Gère l'interface, l'historique, les calculs, ainsi que les fenêtres de graphiques.
    """

    data_changed = Signal()

    def __init__(self):
        """
        Initialise la fenêtre principale.

        - Définit le titre.
        - Charge les données principales et massiques.
        - Crée les variables d'état (fenêtres filles, historique, etc.).
        - Lance initUI() pour configurer l'interface.

        :raises SystemExit:
            Si certains fichiers de données nécessaires (data_masse ou data_materials) 
            sont introuvables ou incomplets.
        """
        super().__init__()
        self.setWindowTitle('LABeCO₂ - Calculateur de Bilan Carbone')

        # Détermine le chemin de base selon le contexte (exécutable ou script)
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(".")

        # Chargement des données principales
        self.data = load_data()

        # Charger les données massiques consommables
        data_masse_path = os.path.join(base_path, 'data_masse_eCO2', 'data_eCO2_masse_consommable.hdf5')#'mock_consumables_100.hdf5')#
        if not os.path.exists(data_masse_path):
            QMessageBox.critical(self, "Erreur", f"Fichier {data_masse_path} introuvable.")
            sys.exit(1)
        self.data_masse = pd.read_hdf(data_masse_path)
        if 'Code NACRES' not in self.data_masse.columns:
            QMessageBox.critical(self, "Erreur", "La colonne 'Code NACRES' est introuvable dans le fichier consommables.")
            sys.exit(1)

        # Chargement des données matériaux
        data_materials_path = os.path.join(base_path, 'data_masse_eCO2', 'empreinte_carbone_materiaux.h5')
        if not os.path.exists(data_materials_path):
            QMessageBox.critical(self, "Erreur", f"Fichier {data_materials_path} introuvable.")
            sys.exit(1)
        self.data_materials = pd.read_hdf(data_materials_path)
        # Assurez-vous que 'Materiau' et 'eCO2_kg' (ou 'Equivalent CO₂ (kg eCO₂/kg)') existent dans self.data_materials

        # Initialisation de variables
        self.calculs = []
        self.calcul_data = []
        self.current_unit = None
        self.total_emissions = 0.0

        # Fenêtres complémentaires
        self.pie_chart_window = None
        self.bar_chart_window = None
        self.proportional_bar_chart_window = None
        self.data_mass_window = None  # Important: initialisation à None
        self.stacked_bar_consumables_window = None

        # Widgets principaux (on les définira vraiment dans initUI())
        self.category_combo = None
        self.subcategory_combo = None
        self.subsub_name_combo = None
        self.year_combo = None
        self.input_field = None
        self.days_field = None
        self.machine_group = None
        self.history_list = None
        self.result_area = None
        self.search_field = None
        self.logo_label = None
        self.header_label = None
        self.input_label = None
        self.days_label = None

        # Spécifique NACRES
        self.conso_filtered_label = None
        self.conso_filtered_combo = None
        self.quantity_label = None
        self.quantity_input = None

        self.setStyleSheet("""
                    QPushButton {
                        background-color: #ffffff; /* Couleur de fond par défaut */
                        border: 1px solid #a9a9a9; /* Bordure fine et grise */
                        border-radius: 4px; /* Coins légèrement arrondis */
                        padding: 2px 8px; /* Espacement interne */
                        font: system; /* Police système par défaut */
                    }
                    QPushButton:hover {
                        background-color: #dde3e8;
                    }

                    QPushButton:pressed {
                        background-color: #b7bcc0;
                    }
        """)

        self.initUI()

    def initUI(self):
        """
        Initialise l'interface graphique de la fenêtre.

        - Crée un layout vertical principal et y insère différentes sections :
          header, selectors, machine, historique, boutons de graphiques, zone de résultat.
        - Place le tout dans un QScrollArea (défilement possible).
        - Redimensionne la fenêtre et connecte quelques signaux de base.
        """
        main_layout = QVBoxLayout()
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 1. Configuration du header (logo + texte d'intro)
        self.initUIHeader(main_layout)

        # 2. Configuration de la sélection de catégories / sous-catégories
        self.initUICategorySelectors(main_layout)

        # 3. Configuration de la section "Machine"
        self.initUIMachineSection(main_layout)

        # 4. Configuration de l'historique et des boutons Export/Import
        self.initUIHistory(main_layout)

        # 5. Configuration des boutons de graphiques
        self.initUIGraphButtons(main_layout)

        # 6. Affichage du total des émissions et source
        main_layout.addWidget(self.result_area)

        # self.source_label = QLabel(
        #     'Les données utilisées ici sont issues de la base de données fournie par <a href="https://labos1point5.org/" style="color:blue; text-decoration:none;">Labo 1point5</a>'
        # )
        # self.source_label.setOpenExternalLinks(True)
        # self.source_label.setAlignment(Qt.AlignCenter)
        # main_layout.addWidget(self.source_label)

        # Remplace l'ancien label par:
        self.sources_label = QLabel("L&#39;ensemble des sources sont à retrouver <a href=\"#\">ici</a>.")
        self.sources_label.setTextFormat(Qt.RichText)  # Interpréter le HTML
        self.sources_label.setOpenExternalLinks(False)  # Ne pas ouvrir le lien dans le navigateur
        self.sources_label.setTextInteractionFlags(Qt.TextBrowserInteraction | Qt.LinksAccessibleByMouse)
        self.sources_label.setAlignment(Qt.AlignCenter)
        self.sources_label.linkActivated.connect(self.show_sources_popup)
        # Ajouter dans le layout
        main_layout.addWidget(self.sources_label)

        # Ajout dans une zone scrollable
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        container = QWidget()
        container.setLayout(main_layout)
        scroll_area.setWidget(container)
        self.setCentralWidget(scroll_area)

        # Connexion des signaux/slots
        self.initUISignals()
        # Mise à jour initiale des sous-catégories
        self.update_subcategories()

        # Définition des tailles de la fenêtre
        self.resize(760, 700)
        screen = QApplication.primaryScreen()
        screen_size = screen.size()
        self.setMaximumSize(screen_size.width(), screen_size.height())
        self.setMinimumSize(700, 700)

    def initUIHeader(self, main_layout):
        """
        Initialise l'entête (header) de l'IU.

        - Ajoute le logo (self.add_logo())
        - Ajoute un texte d'introduction pouvant être "déroulé" ou "enroulé".

        :param main_layout: Le layout parent (QVBoxLayout) dans lequel le header est ajouté.
        :type main_layout: QVBoxLayout
        """

        self.add_logo()
        main_layout.addWidget(self.logo_label)

        self.full_text = '''
        <p>
            Dans un contexte où le respect des <span style="font-weight:bold; color:#2196F3;">Accords de Paris</span> 
            sur le climat est une priorité mondiale, chaque secteur, y compris celui de la recherche, 
            doit contribuer à la <span style="font-weight:bold; color:#1fa543;">réduction des émissions</span> 
            de gaz à effet de serre. Les activités scientifiques, souvent 
            <span style="font-weight:bold; color:#1fa543;">consommatrices de ressources</span>, 
            représentent un levier d’action significatif pour atteindre cet objectif.
        </p>
        <p>
            Cette application vise à <span style="font-weight:bold; color:#1fa543;">calculer le bilan carbone</span> 
            (<span style="font-weight:bold; color:#2196F3;">eCO₂</span>) des activités de laboratoire pour 
            <span style="font-weight:bold; color:#1fa543;">sensibiliser</span> à leur empreinte écologique 
            et identifier les postes les plus énergivores afin d’
            <span style="font-weight:bold; color:#1fa543;">optimiser</span> les pratiques et ainsi 
            <span style="font-weight:bold; color:#1fa543;">réfléchir</span> à des solutions durables 
            pour diminuer son empreinte.
        </p>
        <p>
            L'objectif, à terme, est de pouvoir fournir 
            <span style="font-weight:bold; color:#1fa543;">des solutions concrètes</span> pour
            faire un <span style="font-weight:bold; color:#2196F3;">choix responsable de consommables</span>, 
            ainsi que des conseils sur la <span style="font-weight:bold; color:#2196F3;">gestion des appareils énergivores</span>.
        </p>
        <p>
            Prendre conscience de notre impact environnemental et agir en conséquence est une 
            <span style="font-weight:bold; color:#1fa543;">responsabilité collective</span>. 
            Le secteur scientifique peut, et doit, devenir un acteur exemplaire dans la lutte contre le 
            <span style="font-weight:bold; color:#1fa543;">changement climatique</span>, 
            tout en maintenant l’excellence et l’innovation au cœur de ses priorités.
        </p>
        <p>
            <a href="#" style="color:#1fa543; text-decoration:none;">Voir moins</a>
        </p>
        '''

        self.collapsed_text = '''
        <p>
            Dans un contexte où le respect des <span style="font-weight:bold; color:#2196F3;">Accords de Paris</span> 
            sur le climat est une priorité mondiale, chaque secteur, y compris celui de la recherche, 
            doit contribuer à la <span style="font-weight:bold; color:#1fa543;">réduction des émissions</span> 
            de gaz à effet de serre... 
            <a href="#" style="color:#1fa543; text-decoration:none;">Voir plus</a>
        </p>
        '''

        self.header_label = QLabel()
        self.header_label.setText(self.collapsed_text)
        self.header_label.setWordWrap(True)
        self.header_label.setAlignment(Qt.AlignTop)
        self.header_label.setOpenExternalLinks(False)
        main_layout.addWidget(self.header_label)

    def initUICategorySelectors(self, main_layout):
        """
        Initialise la section de sélection des catégories, sous-catégories,
        sous-sous-catégorie (nom), ainsi que la zone "Consommable" (combo + champ de recherche).

        - Utilise un QFormLayout pour aligner les étiquettes et les champs.
        - Ajoute des widgets pour la quantité, le bouton "Gestion des Consommables", etc.

        :param main_layout: Le layout principal dans lequel on intègre ce formulaire.
        :type main_layout: QVBoxLayout
        """
        # Création des widgets de sélection
        self.category_label = QLabel('Catégorie:')
        self.category_combo = QComboBox()
        categories = self.data['category'].dropna().unique().tolist()
        categories = [cat for cat in categories if cat != 'Électricité']
        categories.append('Machine')
        self.category_combo.addItems(sorted(categories))

        self.subcategory_label = QLabel('Sous-catégorie:')
        self.subcategory_combo = QComboBox()

        self.subsub_name_label = QLabel('Nom:')
        self.subsub_name_combo = QComboBox()
        self.subsub_name_combo.setFixedWidth(200)
        self.search_label = QLabel('Recherche:')
        self.search_field = QLineEdit()
        self.search_field.setFixedWidth(200)

        # Disposition pour la ligne "Nom" avec barre de recherche
        nom_layout = QHBoxLayout()
        nom_layout.addWidget(self.subsub_name_combo)
        nom_layout.addWidget(self.search_label)
        nom_layout.addWidget(self.search_field)

        self.conso_filtered_label = QLabel("Consommable:")
        self.conso_filtered_combo = QComboBox()
        self.conso_filtered_combo.setFixedWidth(200)
        self.conso_search_label = QLabel("Recherche:")
        self.conso_search_field = QLineEdit()
        self.conso_search_field.setFixedWidth(200)

        # Disposition pour la ligne "Consommable" avec barre de recherche
        conso_layout = QHBoxLayout()
        conso_layout.addWidget(self.conso_filtered_combo)
        conso_layout.addWidget(self.conso_search_label)
        conso_layout.addWidget(self.conso_search_field)

        # Création d'un QComboBox pour l'année, caché car non utilisé visuellement
        
        self.year_combo = QComboBox(parent=self)
        self.year_combo.setVisible(False)
        
        # self.year_label = QLabel('Année:')
        # self.year_combo = QComboBox()

        # Autres widgets
        self.quantity_label = QLabel("Quantité:")
        self.quantity_input = QLineEdit()
        self.quantity_label.setVisible(False)
        self.quantity_input.setVisible(False)

      

        self.manage_consumables_button = QPushButton("Gestion des Consommables")
        self.manage_consumables_button.setStyleSheet("""
            QPushButton {
                text-decoration: underline;
                color: blue;
                background: none;
                border: none;
                padding: 0;
            }
            QPushButton:hover {
                color: darkblue;
            }
        """)
        self.manage_consumables_button.clicked.connect(self.open_data_mass_window)

        self.input_label = QLabel('Entrez la valeur:')
        self.input_field = QLineEdit()
        self.input_field.setEnabled(False)

        self.days_label = QLabel("Nombre de jours d'utilisation:")
        self.days_field = QLineEdit()
        self.days_field.setEnabled(False)
        self.days_label.setVisible(False)
        self.days_field.setVisible(False)

        self.calculate_button = QPushButton('Calculer le Bilan Carbone')
        self.calculate_button.setToolTip(
            "Calcule le bilan carbone sélectionné et tente également le calcul via la masse si possible."
        )

        # Utilisation de QFormLayout pour aligner les champs
        form_layout = QFormLayout()
        form_layout.setSpacing(5)
        form_layout.setLabelAlignment(Qt.AlignRight)

        form_layout.addRow(self.category_label, self.category_combo)
        form_layout.addRow(self.subcategory_label, self.subcategory_combo)
        form_layout.addRow(self.subsub_name_label, nom_layout)
        form_layout.addRow(self.conso_filtered_label, conso_layout)


        # Disposition verticale principale
        existing_layout = QVBoxLayout()
        existing_layout.setSpacing(5)
        existing_layout.addLayout(form_layout)

        # Ajout des éléments suivants sous le formulaire
        existing_layout.addWidget(self.quantity_label)
        existing_layout.addWidget(self.quantity_input)
        existing_layout.addWidget(self.manage_consumables_button)
        existing_layout.addWidget(self.input_label)
        existing_layout.addWidget(self.input_field)
        existing_layout.addWidget(self.days_label)
        existing_layout.addWidget(self.days_field)
        existing_layout.addWidget(self.calculate_button)

        # Intégration dans le layout global
        existing_group = QWidget()
        existing_group.setLayout(existing_layout)
        main_layout.addWidget(existing_group)

    def initUIMachineSection(self, main_layout):
        """
        Initialise la section de l'interface dédiée aux Machines.

        - Crée un formulaire (QFormLayout) avec champs pour la machine (puissance, 
          temps d'utilisation, jours, type d'électricité, etc.).
        - Stocke ce formulaire dans self.machine_group, masqué par défaut.

        :param main_layout: Layout principal où insérer la section Machines.
        :type main_layout: QVBoxLayout
        """
        self.machine_name_label = QLabel('Nom de la machine:')
        self.machine_name_field = QLineEdit()
        self.machine_name_field.setMaximumWidth(200)

        self.power_label = QLabel('Puissance de la machine (kW):')
        self.power_field = QLineEdit()
        self.power_field.setMaximumWidth(200)

        self.usage_time_label = QLabel("Temps d'utilisation par jour (heures):")
        self.usage_time_field = QLineEdit()
        self.usage_time_field.setMaximumWidth(200)
        self.usage_time_field.setValidator(QIntValidator(1, 24, self))

        self.days_machine_label = QLabel("Nombre de jours d'utilisation:")
        self.days_machine_field = QLineEdit()
        self.days_machine_field.setMaximumWidth(200)

        self.electricity_label = QLabel('Type d\'électricité:')
        self.electricity_combo = QComboBox()
        self.electricity_combo.setMaximumWidth(200)

        electricity_types = self.data[self.data['category'] == 'Électricité']['name'].dropna().unique()
        self.electricity_combo.addItems(sorted(electricity_types))

        self.add_machine_button = QPushButton('Ajouter la machine')

        self.machine_layout = QFormLayout()
        self.machine_layout.addRow(self.machine_name_label, self.machine_name_field)
        self.machine_layout.addRow(self.power_label, self.power_field)
        self.machine_layout.addRow(self.usage_time_label, self.usage_time_field)
        self.machine_layout.addRow(self.days_machine_label, self.days_machine_field)
        self.machine_layout.addRow(self.electricity_label, self.electricity_combo)
        self.machine_layout.addRow(self.add_machine_button)

        self.machine_group = QWidget()
        self.machine_group.setLayout(self.machine_layout)
        self.machine_group.setVisible(False)

        main_layout.addWidget(self.machine_group)

    def initUIHistory(self, main_layout):
        """
        Initialise l'historique des calculs.

        - Ajoute une QListWidget pour lister les calculs.
        - Ajoute des boutons de suppression, modification, export et import.
        - Ajoute un QLabel (self.result_area) pour afficher le total des émissions.

        :param main_layout: Layout vertical principal où insérer l'historique.
        :type main_layout: QVBoxLayout
        """
        self.history_label = QLabel('Historique des calculs:')
        main_layout.addWidget(self.history_label)

        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(100)

        history_scroll = QScrollArea()
        history_scroll.setWidgetResizable(True)
        history_scroll.setWidget(self.history_list)
        history_scroll.setFixedHeight(100)
        main_layout.addWidget(history_scroll)

        self.delete_button = QPushButton('Supprimer le calcul sélectionné')
        self.modify_button = QPushButton('Modifier le calcul sélectionné')

        calc_buttons_layout = QHBoxLayout()
        calc_buttons_layout.setSpacing(1)
        calc_buttons_layout.addWidget(self.delete_button)
        calc_buttons_layout.addWidget(self.modify_button)

        self.export_button = QPushButton('Exporter les données')
        self.import_button = QPushButton('Importer les données')

        export_import_layout = QHBoxLayout()
        export_import_layout.setSpacing(0)
        export_import_layout.addWidget(self.export_button)
        export_import_layout.addWidget(self.import_button)

        buttons_group_layout = QVBoxLayout()
        buttons_group_layout.setSpacing(0)
        buttons_group_layout.addLayout(calc_buttons_layout)
        buttons_group_layout.addLayout(export_import_layout)

        main_layout.addLayout(buttons_group_layout)
        main_layout.addSpacing(5)

        self.result_area = QLabel("Total des émissions : 0.0000 kg CO₂e")

    def initUIGraphButtons(self, main_layout):
        """
        Initialise la zone des boutons de génération de graphiques.

        - Ajoute plusieurs boutons (camembert, barres empilées, etc.) sur deux lignes.
        - Chaque bouton est relié à une méthode spécifique (generate_*).

        :param main_layout: Layout principal où les boutons sont disposés.
        :type main_layout: QVBoxLayout
        """
        graph_summary_label = QLabel("Générer des résumés graphiques :")
        main_layout.addWidget(graph_summary_label)

        self.generate_pie_button = QPushButton('Diagramme en Secteurs')
        self.generate_pie_button.setToolTip("Affiche un diagramme en secteurs...")

        self.generate_bar_button = QPushButton('Barres Empilées à 100%')
        self.generate_bar_button.setToolTip("Affiche un graphique à barres empilées à 100%...")

        self.generate_proportional_bar_button = QPushButton('Barres Empilées')
        self.generate_proportional_bar_button.setToolTip("Affiche un graphique à barres empilées proportionnelles...")

        buttons_layout_graph_line1 = QHBoxLayout()
        buttons_layout_graph_line1 .addWidget(self.generate_pie_button)
        buttons_layout_graph_line1 .addWidget(self.generate_bar_button)
        buttons_layout_graph_line1 .addWidget(self.generate_proportional_bar_button)
        main_layout.addLayout(buttons_layout_graph_line1)

        self.generate_stacked_bar_consumables_button = QPushButton("Barres Empilées (Consommables)")
        self.generate_stacked_bar_consumables_button.setToolTip(
            "Affiche un graphique en barres empilées uniquement pour les consommables à quantité > 0."
        )

        self.generate_nacres_bar_button = QPushButton("Barres NACRES")
        self.generate_nacres_bar_button.clicked.connect(self.generate_nacres_bar_chart)

        buttons_layout_graph_line2 = QHBoxLayout()
        buttons_layout_graph_line2.addWidget(self.generate_stacked_bar_consumables_button)
        buttons_layout_graph_line2.addWidget(self.generate_nacres_bar_button)
        main_layout.addLayout(buttons_layout_graph_line2)

        main_layout.addSpacing(5)

    def initUISignals(self):
        """
        Connecte tous les signaux/slots de l'interface.

        - Liaison des QComboBox (catégorie, sous-catégorie...) à leurs fonctions de mise à jour.
        - Liaison des boutons (calculate_button, export_button, etc.) à leurs callbacks.
        - Liaison des double-clics dans l'historique pour modifier un item.
        - Liaison du champ de recherche "search_field" et conso_search_field.
        - Liaison du bouton "Ajouter la machine".
        """
        # Lien du header "voir plus/voir moins"
        self.header_label.linkActivated.connect(self.toggle_text_display)

        # Quand la catégorie change
        self.category_combo.currentIndexChanged.connect(self.update_subcategories)

        # Quand la sous-catégorie change
        self.subcategory_combo.currentIndexChanged.connect(self.update_subsubcategory_names)

        # Ajout : on veut aussi vérifier la visibilité des consommables
        self.subcategory_combo.currentIndexChanged.connect(self.update_nacres_visibility)

        # Barre de recherche spécifique NACRES
        self.conso_search_field.textChanged.connect(
            lambda text: self.update_conso_filtered_combo(filter_text=text)
        )

        # Quand le texte de recherche change => on passe par la fonction on_search_text_changed
        self.search_field.textChanged.connect(self.on_search_text_changed)

        # Sous-sous-catégorie
        self.subsub_name_combo.currentIndexChanged.connect(self.update_years)
        self.subsub_name_combo.currentIndexChanged.connect(self.on_subsub_name_changed)

        # Quand l'année change
        self.year_combo.currentIndexChanged.connect(self.update_unit)
        self.year_combo.currentIndexChanged.connect(self.update_conso_filtered_combo)

        # Boutons
        self.calculate_button.clicked.connect(self.calculate_emission)
        self.delete_button.clicked.connect(self.delete_selected_calculation)
        self.modify_button.clicked.connect(self.modify_selected_calculation)
        self.export_button.clicked.connect(self.export_data)
        self.import_button.clicked.connect(self.import_data)

        # Graphiques
        self.generate_pie_button.clicked.connect(self.generate_pie_chart)
        self.generate_bar_button.clicked.connect(self.generate_bar_chart)
        self.generate_proportional_bar_button.clicked.connect(self.generate_proportional_bar_chart)
        self.generate_stacked_bar_consumables_button.clicked.connect(self.generate_stacked_bar_consumables)


        # Historique : double-clic => modifier
        self.history_list.itemDoubleClicked.connect(self.modify_selected_calculation)

        # Machines
        self.add_machine_button.clicked.connect(self.add_machine)

        # NACRES
        self.conso_filtered_combo.currentIndexChanged.connect(self.on_conso_filtered_changed)

    def on_search_text_changed(self, text):
        """
        Gère le changement de texte dans la barre de recherche principale (search_field).

        - Met à jour les sous-sous-catégories (update_subsubcategory_names).
        - Met à jour la liste des consommables (update_conso_filtered_combo).
        - Synchronise l'interface (synchronize_after_search).

        :param text: Texte actuel saisi dans le champ de recherche.
        :type text: str
        """
        self.update_subsubcategory_names()
        self.update_conso_filtered_combo(filter_text=None)
        self.synchronize_after_search()

    def synchronize_after_search(self):
        """
        Synchronise l'IU après une recherche.

        - Si la combo subsub_name_combo ne contient qu'une seule option (outre "non renseignée"), 
          la sélectionne automatiquement.
        - Même logique pour conso_filtered_combo (consommables).
        - Met à jour la visibilité du champ "quantité".
        """
        # SUBSUB
        count_subsub = self.subsub_name_combo.count()
        # Normalement, on a au moins "non renseignée"
        if count_subsub == 2:
            # => On sélectionne directement la 2ème
            self.subsub_name_combo.setCurrentIndex(1)

        # NACRES
        count_nacres = self.conso_filtered_combo.count()
        if count_nacres == 2:
            self.conso_filtered_combo.setCurrentIndex(1)

        # Vérifie si on doit montrer/cacher la quantité
        self.update_quantity_visibility()

    def update_subcategories(self):
        """
        Met à jour la liste des sous-catégories en fonction de la catégorie sélectionnée.

        - Si la catégorie = "Machine", masque les champs relatifs aux consommables/achats/etc. 
          et affiche la section Machine.
        - Sinon, réaffiche les champs généraux, met à jour la combo subcategory_combo 
          depuis self.data, et appelle update_subsubcategory_names() + update_nacres_visibility().
        - Gère aussi l'affichage/masquage du champ days (véhicules).
        """
        category = self.category_combo.currentText()

        if category == 'Machine':
            # Masquer les champs "Achats/Véhicules/etc." non pertinents pour Machine
            self.subcategory_label.setVisible(False)
            self.subcategory_combo.setVisible(False)
            self.search_label.setVisible(False)
            self.search_field.setVisible(False)
            self.subsub_name_label.setVisible(False)
            self.subsub_name_combo.setVisible(False)
            self.year_combo.setVisible(False)
            self.input_label.setVisible(False)
            self.input_field.setVisible(False)
            self.days_label.setVisible(False)
            self.days_field.setVisible(False)
            self.calculate_button.setVisible(False)

            # Afficher le formulaire "Machine"
            self.machine_group.setVisible(True)
            self.machine_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

            # Cacher le bouton « Gestion des Consommables »
            self.manage_consumables_button.setVisible(False)

            # Cacher intégralement la zone "Consommable" (liste et barre de recherche)
            self.conso_filtered_label.setVisible(False)
            self.conso_filtered_combo.setVisible(False)
            self.conso_search_label.setVisible(False)
            self.conso_search_field.setVisible(False)
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)

        else:
            # Réafficher les widgets pour les autres catégories
            self.subcategory_label.setVisible(True)
            self.subcategory_combo.setVisible(True)
            self.search_label.setVisible(True)
            self.search_field.setVisible(True)
            self.subsub_name_label.setVisible(True)
            self.subsub_name_combo.setVisible(True)
            self.year_combo.setVisible(True)
            self.input_label.setVisible(True)
            self.input_field.setVisible(True)
            self.calculate_button.setVisible(True)

            # Cacher la zone "Machine"
            self.machine_group.setVisible(False)
            self.machine_group.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            self.manage_consumables_button.setVisible(True)

            # Mettre à jour la combo sous-catégorie
            subcategories = self.data[self.data['category'] == category]['subcategory'].dropna().unique()
            self.subcategory_combo.clear()
            self.subcategory_combo.addItems(sorted(subcategories.astype(str)))

            # Met à jour la sous-sous-catégorie et la visibilité NACRES (pour "Achats"+"Consommables" etc.)
            self.update_subsubcategory_names()
            self.update_nacres_visibility()

            # Cas particulier : Véhicules => on affiche le champ "nombre de jours"
            if category == "Véhicules":
                self.days_label.setVisible(True)
                self.days_field.setVisible(True)
                self.days_field.setEnabled(True)
            else:
                self.days_label.setVisible(False)
                self.days_field.setVisible(False)
                self.days_field.setEnabled(False)

    def update_subsubcategory_names(self):
        """
        Met à jour la combo subsub_name_combo (sous-sous-catégorie) en fonction 
        de la catégorie, sous-catégorie et éventuellement d'un texte de recherche.

        - Construit une liste "subsubcategory - name" pour chaque ligne correspondante de self.data.
        - Insère "non renseignée" en premier.
        - Appelle ensuite self.update_years() pour alimenter year_combo.
        """
        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        search_text = self.search_field.text().lower()

        # Filtrage principal
        mask = (self.data['category'] == category)
        if subcategory:
            mask &= (self.data['subcategory'] == subcategory)

        filtered_data = self.data[mask]

        # Construction des libellés "subsubcategory - name"
        subsub_names = (
            filtered_data['subsubcategory'].fillna('')
            + ' - '
            + filtered_data['name'].fillna('')
        ).str.strip(' - ')

        subsub_names_unique = subsub_names.unique()

        # Application du filtrage par le champ de recherche
        if search_text:
            subsub_names_filtered = [s for s in subsub_names_unique if search_text in s.lower()]
        else:
            subsub_names_filtered = list(subsub_names_unique)

        # On ajoute "non renseignée" tout en haut
        subsub_names_filtered.insert(0, "non renseignée")

        self.subsub_name_combo.blockSignals(True)
        self.subsub_name_combo.clear()
        non_renseignee = subsub_names_filtered.pop(0)
        subsub_names_filtered = sorted(subsub_names_filtered)
        subsub_names_filtered.insert(0, non_renseignee)
        self.subsub_name_combo.addItems(subsub_names_filtered)
        self.subsub_name_combo.blockSignals(False)

        self.update_years()

    def update_years(self):
        """
        Met à jour la combo year_combo en fonction de la catégorie, sous-catégorie 
        et sous-sous-catégorie sélectionnées.

        - Construit un masque sur self.data et récupère la colonne 'year'.
        - Insère ces années dans year_combo, puis appelle update_unit() 
          pour ajuster le champ "Entrez la valeur".
        """
        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        subsub_name = self.subsub_name_combo.currentText()
        subsubcategory, name = self.split_subsub_name(subsub_name)

        mask = (
            (self.data['category'] == category) &
            (self.data['subcategory'] == subcategory) &
            (self.data['subsubcategory'].fillna('') == subsubcategory) &
            (self.data['name'].fillna('') == name)
        )
        years = self.data[mask]['year'].dropna().astype(str).unique()

        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        self.year_combo.addItems(sorted(years))
        self.year_combo.blockSignals(False)
        self.update_unit()

    def update_unit(self):
        """
        Met à jour l'unité (self.current_unit) et active/désactive le champ input_field 
        selon la correspondance trouvée dans self.data.

        - Construit un masque (catégorie, sous-catégorie, sub-sub-cat, name, year).
        - Si une ligne est trouvée, self.current_unit devient l'unité (ex: euro, km...).
          Le champ input_field est activé et son label est mis à jour.
        - Sinon, le champ input_field reste désactivé.
        """
        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        subsub_name = self.subsub_name_combo.currentText()
        year = self.year_combo.currentText()
        subsubcategory, name = self.split_subsub_name(subsub_name)

        mask = (
            (self.data['category'] == category) &
            (self.data['subcategory'] == subcategory) &
            (self.data['subsubcategory'].fillna('') == subsubcategory) &
            (self.data['name'].fillna('') == name)#&
            # (self.data['year'].astype(str) == year)
        )
         # Si on a un year non vide, on ajoute la condition
        if year:
            mask &= (self.data['year'].astype(str) == year)


        filtered_data = self.data[mask]
        if not filtered_data.empty:
            unit = filtered_data['unit'].values[0] or 'valeur'
            self.current_unit = unit
            self.input_label.setText(f'Entrez la valeur en {unit}:')
            self.input_field.setEnabled(True)
        else:
            self.current_unit = None
            self.input_label.setText('Entrez la valeur:')
            self.input_field.setEnabled(False)

    def update_conso_filtered_combo(self, filter_text=None):
        """
        Met à jour la combo conso_filtered_combo (liste des consommables NACRES) 
        en fonction d'un texte de filtre (filter_text).

        - Vide la combo et ajoute "non renseignée".
        - Parcourt self.data_masse et insère dans la combo tous les consommables 
          dont le display_text correspond au filtre (s'il existe).
        - Met à jour la visibilité de la quantité.

        :param filter_text: Texte de recherche optionnel. Si None, pas de filtrage.
        :type filter_text: str or None
        """
        self.conso_filtered_combo.blockSignals(True)
        self.conso_filtered_combo.clear()
        self.conso_filtered_combo.addItem("non renseignée")

        # Définir le texte de filtrage
        if filter_text is None:
            # Si aucun filtre spécifique, on peut laisser la liste complète
            filter_text = ""
        else:
            filter_text = filter_text.lower()

        # Parcourir les données pour remplir la combo selon le filtre
        for idx, row in self.data_masse.iterrows():
            code_nacres = row.get('Code NACRES', '').strip()
            consommable = row.get('Consommable', '').strip()
            display_text = f"{code_nacres} - {consommable}"

            # Ajouter l'item s'il correspond au filtre ou si aucun filtre n'est saisi
            if not filter_text or filter_text in display_text.lower():
                self.conso_filtered_combo.addItem(display_text)

        self.conso_filtered_combo.blockSignals(False)
        self.update_quantity_visibility()

    def on_subsub_name_changed(self):
        """
        Gère la sélection d'une sous-sous-catégorie (subsub_name).

        - Récupère les 4 premiers caractères comme code NACRES approximatif.
        - Filtre self.data_masse pour ne garder que les consommables 
          dont 'Code NACRES' commence par ce code.
        - Met à jour la combo conso_filtered_combo avec cette liste restreinte.
        - Affiche le champ quantité si nécessaire.
        """

        subsub_name = self.subsub_name_combo.currentText()
        
        # Cas "non renseignée"
        if not subsub_name or subsub_name == "non renseignée":
            self.conso_filtered_combo.blockSignals(True)
            self.conso_filtered_combo.clear()
            self.conso_filtered_combo.addItem("non renseignée")
            self.conso_filtered_combo.blockSignals(False)

            # Masquer ou réinitialiser la quantité
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)
            return

        # Extraire le "code NACRES" sur les 4 premiers caractères
        # Exemple: "NB13 - Culture cellulaire" => code_nacres_4 = "NB13"
        code_nacres_4 = subsub_name[:4]

        # On va reconstruire la combo conso_filtered_combo en filtrant self.data_masse
        filtered_items = []
        for idx, row in self.data_masse.iterrows():
            full_code = row.get('Code NACRES', '').strip()  # ex. "NB13"
            consommable = row.get('Consommable', '').strip()
            display_text = f"{full_code} - {consommable}"

            # On compare le début du code NACRES
            if full_code.startswith(code_nacres_4):
                filtered_items.append(display_text)

        # Actualiser la combo NACRES avec les seuls éléments filtrés
        self.conso_filtered_combo.blockSignals(True)
        self.conso_filtered_combo.clear()
        self.conso_filtered_combo.addItem("non renseignée")
        for item_text in sorted(filtered_items):
            self.conso_filtered_combo.addItem(item_text)
        self.conso_filtered_combo.blockSignals(False)

        # Optionnel : si un seul consommable correspond, on peut l’auto-sélectionner :
        if len(filtered_items) == 1:
            self.conso_filtered_combo.setCurrentIndex(1)
        else:
            self.conso_filtered_combo.setCurrentIndex(0)

        # Afficher la quantité si on n’est pas sur "non renseignée"
        self.update_quantity_visibility()

    def on_conso_filtered_changed(self):
        """
        Quand on change de consommable NACRES dans conso_filtered_combo :

        - Si "non renseignée", on masque quantité et désactive le champ euro.
        - Sinon, on force la catégorie "Achats" et la sous-catégorie contenant "Consommables",
          on actualise subsub_name_combo (via update_subsubcategory_names),
          on tente de sélectionner la sous-sous-catégorie correspondant au code NACRES,
          puis on appelle update_unit() pour activer le champ euro si une ligne existe.
        """
        selected_text = self.conso_filtered_combo.currentText()
        if not selected_text or selected_text == "non renseignée":
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)
            # Forcer subsub_name à "non renseignée"
            self.subsub_name_combo.blockSignals(True)
            idx_nr = self.subsub_name_combo.findText("non renseignée")
            self.subsub_name_combo.setCurrentIndex(idx_nr if idx_nr != -1 else -1)
            self.subsub_name_combo.blockSignals(False)

            self.update_unit()  # désactiver le champ euro
            return

        # On parse les 4 premiers caractères comme "code_nacres_4"
        # Ex: "NB13 - Culture cellulaire" => code_nacres_4 = "NB13"
        code_nacres_4 = selected_text[:4]

        # Forcer la Catégorie = "Achats"
        idx_cat = self.category_combo.findText("Achats")
        if idx_cat >= 0:
            self.category_combo.blockSignals(True)
            self.category_combo.setCurrentIndex(idx_cat)
            self.category_combo.blockSignals(False)

        # Forcer la Sous-catégorie contenant "Consommables"
        target_subcat = None
        for i in range(self.subcategory_combo.count()):
            txt = self.subcategory_combo.itemText(i)
            if "Consommables" in txt:
                target_subcat = txt
                break
        if target_subcat is not None:
            idx_sub = self.subcategory_combo.findText(target_subcat)
            if idx_sub != -1:
                self.subcategory_combo.blockSignals(True)
                self.subcategory_combo.setCurrentIndex(idx_sub)
                self.subcategory_combo.blockSignals(False)

        # Actualiser la combo subsub_name en fonction de cat & subcat
        self.update_subsubcategory_names()

        # On cherche la (première) ligne subsubcategory[:4] == code_nacres_4
        filtered_data = self.data[
            (self.data['category'] == "Achats") &
            (self.data['subcategory'].str.contains("Consommables", na=False)) &
            (self.data['subsubcategory'].fillna('').str[:4] == code_nacres_4)
        ]
        if filtered_data.empty:
            # Rien trouvé => subsub_name = "non renseignée"
            self.subsub_name_combo.blockSignals(True)
            idx_nr = self.subsub_name_combo.findText("non renseignée")
            self.subsub_name_combo.setCurrentIndex(idx_nr if idx_nr != -1 else -1)
            self.subsub_name_combo.blockSignals(False)
        else:
            row = filtered_data.iloc[0]
            real_subsub = row['subsubcategory'] or ''
            real_name = row['name'] or ''
            new_subsub_text = f"{real_subsub} - {real_name}".strip(" - ")

            # Essayer de sélectionner cette valeur dans subsub_name_combo
            self.subsub_name_combo.blockSignals(True)
            idx_ss = self.subsub_name_combo.findText(new_subsub_text)
            if idx_ss != -1:
                self.subsub_name_combo.setCurrentIndex(idx_ss)
            else:
                # Sinon, on l'ajoute
                self.subsub_name_combo.addItem(new_subsub_text)
                self.subsub_name_combo.setCurrentIndex(self.subsub_name_combo.count() - 1)
            self.subsub_name_combo.blockSignals(False)

        # Afficher la quantité
        self.quantity_label.setVisible(True)
        self.quantity_input.setVisible(True)

        # Appel final de update_unit (pour activer le champ euro si la ligne existe)
        self.update_unit()

    def update_quantity_visibility(self):
        """
        Affiche ou masque les champs "Quantité" (quantity_label, quantity_input) 
        selon la sélection actuelle dans conso_filtered_combo.
        """
        current_nacres = self.conso_filtered_combo.currentText()
        if (not current_nacres) or (current_nacres == "non renseignée"):
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)
        else:
            self.quantity_label.setVisible(True)
            self.quantity_input.setVisible(True)

    def add_logo(self):
        """
        Charge et affiche le logo dans self.logo_label.

        - Utilise load_logo() pour obtenir le chemin du logo.
        - Redimensionne l'image à 150×150 en conservant les proportions.
        - Affiche un QMessageBox d'avertissement si l'image est introuvable.
        """
        logo_path = load_logo()
        self.logo_label = QLabel()
        pixmap = QPixmap(logo_path)
        if pixmap.isNull():
            QMessageBox.warning(self, 'Erreur', f"Impossible de charger l'image : {logo_path}")
        else:
            resized_pixmap = pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(resized_pixmap)
            self.logo_label.setAlignment(Qt.AlignCenter)

    def toggle_text_display(self):
        """
        Alterne le texte d'introduction entre une version "réduite" et une version "complète".

        - Se base sur self.collapsed_text et self.full_text pour remplacer le contenu 
          de self.header_label.
        """
        if self.header_label.text() == self.collapsed_text:
            self.header_label.setText(self.full_text)
        else:
            self.header_label.setText(self.collapsed_text)

    def split_subsub_name(self, subsub_name):
        """
        Sépare une chaîne de type "subsubcategory - name" en deux parties.

        :param subsub_name: Le texte à scinder (ex. "NB13 - Culture cellulaire").
        :type subsub_name: str
        :return: Un tuple (subsubcategory, name).
        :rtype: tuple(str, str)
        """
        if ' - ' in subsub_name:
            subsubcategory, name = subsub_name.split(' - ', 1)
        else:
            subsubcategory = ''
            name = subsub_name
        return subsubcategory.strip(), name.strip()

    def calculate_emission(self):
        """
        Calcule les émissions carbone en fonction de la catégorie/sous-catégorie/sub-sous-catégorie 
        et la valeur saisie, en gérant l'incertitude.

        - Si la catégorie est 'Machine', redirige vers add_machine().
        - Sinon, récupère l'unité, le facteur d'émission + incertitude dans self.data, et effectue un calcul 
        (emissions_price, emissions_price_error).
        - Si NACRES (consommable) est renseigné, appelle calculate_mass_based_emissions() 
        pour obtenir (emission_mass, emission_mass_error).
        - Stocke le tout (y compris les incertitudes) dans l'historique 
        et met à jour le total (update_total_emissions).
        """
        print("calculate_emission appelé")

        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        subsub_name = self.subsub_name_combo.currentText()
        year = self.year_combo.currentText()
        subsubcategory, category_nacres = self.split_subsub_name(subsub_name)

        # Cas spécial : Machine => gestion dans add_machine()
        if category == 'Machine':
            self.add_machine()
            self.input_field.clear()
            self.update_total_emissions()
            self.data_changed.emit()
            return

        # Code NACRES par défaut
        code_nacres = 'NA'
        consommable = 'NA'
        if category == 'Achats' and subsubcategory:
            code_nacres = subsubcategory[:4]

        # Récup combo NACRES
        selected_nacres = (
            self.conso_filtered_combo.currentText()
            if self.conso_filtered_combo.isVisible()
            else None
        )
        has_nacres_match = selected_nacres and selected_nacres != "non renseignée"
        if has_nacres_match and " - " in selected_nacres:
            code_nacres, consommable = selected_nacres.split(" - ", 1)

        # Récup la valeur (en euros, km, etc.)
        try:
            input_text = self.input_field.text().strip().replace(',', '.')
            value = float(input_text)
            if value < 0:
                raise ValueError("La valeur doit être positive.")
        except ValueError:
            QMessageBox.warning(self, 'Erreur', 'Veuillez entrer une valeur numérique positive valide.')
            return

        # Nombre de jours
        days = int(self.days_field.text()) if self.days_field.isEnabled() and self.days_field.text() else 1
        total_value = value * days

        # Recherche du facteur d’émission dans self.data (et incertitude)
        mask = (
            (self.data['category'] == category) &
            (self.data['subcategory'] == subcategory) &
            (self.data['subsubcategory'].fillna('') == subsubcategory) &
            (self.data['name'].fillna('') == category_nacres)
        )
        if year:
            mask &= (self.data['year'].astype(str) == year)

        filtered_data = self.data[mask]
        if filtered_data.empty:
            self.result_area.setText('Aucune donnée disponible pour cette sélection.')
            return

        total_emission_factor = filtered_data['total'].values[0]
        # Lire l'incertitude (ex. 0.1 => 10%)
        factor_uncert = filtered_data.get('uncertainty', 0.0)
        if isinstance(factor_uncert, pd.Series):  # si c'est une série, prendre la 1ère valeur
            factor_uncert = factor_uncert.values[0]
        factor_uncert = float(factor_uncert) if factor_uncert else 0.0

        # Émissions par le prix
        emissions = total_value * total_emission_factor
        emissions_error = emissions * factor_uncert  # incertitude absolue

        # Gestion des émissions massiques via NACRES
        quantity = 0
        if self.quantity_label.isVisible() and self.quantity_input.isVisible():
            try:
                quantity_str = self.quantity_input.text().strip()
                quantity = int(quantity_str) if quantity_str else 0
            except:
                quantity = 0

        emission_massique, total_mass, emission_mass_error = (None, None, None)
        if has_nacres_match:
            emission_massique, total_mass, emission_mass_error = self.calculate_mass_based_emissions(code_nacres, quantity=quantity)

        new_data = {
            'category': category,
            'subcategory': subcategory,
            'subsubcategory': subsubcategory,
            'name': category_nacres,
            'value': total_value,
            'unit': self.current_unit,
            'emissions_price': emissions,
            'emissions_price_error': emissions_error,
            'emission_mass': emission_massique if emission_massique is not None else None,
            'emission_mass_error': emission_mass_error if emission_mass_error is not None else None,
            'total_mass': total_mass if total_mass is not None else None,
            'code_nacres': code_nacres,
            'consommable': consommable,
            'days': days,
            'quantity': quantity,
        }

        print("DEBUG new_data in creation:", new_data)
        self.create_or_update_history_item(new_data)

        self.update_total_emissions()
        self.input_field.clear()
        self.data_changed.emit()

    def update_total_emissions(self):
        """
        Recalcule et affiche la somme totale des émissions (en kg CO₂e) 
        figurant dans l'historique, en incluant la somme des incertitudes 
        (en quadrature).

        - Parcourt self.history_list, lit 'emissions_price' et 'emissions_price_error'.
        - Calcule le total des émissions ET le total d'incertitude (somme en quadrature).
        - Même logique pour la partie mass-based (emission_mass / emission_mass_error).
        - Met à jour self.result_area.
        """
        import math

        total_emissions = 0.0
        total_emissions_error_sq = 0.0

        total_mass_emissions_conso = 0.0
        total_mass_emissions_conso_error_sq = 0.0

        for i in range(self.history_list.count()):
            item = self.history_list.item(i)
            data = item.data(Qt.UserRole)
            if data:
                # Prix
                e_price = float(data.get('emissions_price', 0.0))
                e_price_err = float(data.get('emissions_price_error', 0.0))
                total_emissions += e_price
                total_emissions_error_sq += (e_price_err**2)

                # Masse
                e_mass = float(data.get('emission_mass', 0.0) or 0.0)
                e_mass_err = float(data.get('emission_mass_error', 0.0) or 0.0)
                total_mass_emissions_conso += e_mass
                total_mass_emissions_conso_error_sq += (e_mass_err**2)

        total_emissions_error = math.sqrt(total_emissions_error_sq)
        total_mass_emissions_conso_error = math.sqrt(total_mass_emissions_conso_error_sq)

        self.total_emissions = total_emissions  # vous pouvez garder ça pour d'autres usages
        # idem pour self.total_mass_emissions_conso, etc.

        # Mettre à jour l'affichage
        self.result_area.setText(
            f"Total des émissions (prix) : {total_emissions:.4f} ± {total_emissions_error:.4f} kg CO₂e\n"
            f"Émission des consommables (masse) : {total_mass_emissions_conso:.4f} ± {total_mass_emissions_conso_error:.4f} kg CO₂e"
        )

    def delete_selected_calculation(self):
        """
        Supprime l'entrée actuellement sélectionnée dans l'historique (history_list).

        - Si aucune entrée n'est sélectionnée, ne fait rien.
        - Met à jour ensuite le total des émissions (update_total_emissions).
        - Émet le signal data_changed.
        """
        selected_row = self.history_list.currentRow()
        if selected_row >= 0:
            self.history_list.takeItem(selected_row)
            self.update_total_emissions()
            self.data_changed.emit()

    def modify_selected_calculation(self):
        """
        Ouvre un EditCalculationDialog pour modifier l'entrée actuellement sélectionnée 
        dans l'historique. Puis recalcule les émissions et met à jour l'item.
        """
        selected_item = self.history_list.currentItem()
        if not selected_item:
            QMessageBox.warning(self, 'Erreur', 'Veuillez sélectionner un calcul à modifier.')
            return

        data = selected_item.data(Qt.UserRole)
        if not data:
            QMessageBox.warning(self, 'Erreur', 'Aucune donnée disponible pour cet élément.')
            return

        # Ouvrir la dialog d'édition
        dialog = EditCalculationDialog(
            parent=self,
            data=data,
            main_data=self.data,
            data_masse=self.data_masse,
            data_materials=self.data_materials
        )
        if dialog.exec() == QDialog.Accepted:
            modified_data = dialog.modified_data
            print("Debug - Nouveau self.modified_data :", modified_data)

            # Désormais, recalculate_emissions renvoie 5 valeurs :
            # (ep, ep_err, em, em_err, tm)
            ep, ep_err, em, em_err, tm = self.recalculate_emissions(modified_data)

            # Si ep est None => problème dans le recalc => on arrête
            if ep is None:
                return

            # Mettre à jour modified_data avec tous les champs recalculés
            modified_data['emissions_price'] = ep
            modified_data['emissions_price_error'] = ep_err
            modified_data['emission_mass'] = em
            modified_data['emission_mass_error'] = em_err
            modified_data['total_mass'] = tm  # <-- important pour afficher la masse

            # Retire l'ancien item de l'historique
            self.history_list.takeItem(self.history_list.row(selected_item))

            # Crée un nouvel item, actualisé
            self.create_or_update_history_item(modified_data)

            # Met à jour le total
            self.update_total_emissions()
            self.data_changed.emit()

    def recalculate_emissions(self, data):
        """
        Recalcule les émissions CO₂ à partir d'un dictionnaire de données (data).

        - Si la catégorie == 'Machine', recalcule en fonction de la consommation (kWh) * facteur d'émission
        et retourne 5 valeurs (emissions_price, emissions_price_error, emission_mass=0, emission_mass_error=0, total_mass=0).
        - Sinon, on recherche le 'total_emission_factor' + incertitude dans self.data (même logique que calculate_emission).
        On calcule :
            emissions_price = total_value * factor
            emissions_price_error = emissions_price * factor_uncert
        - Si category == 'Achats' et code_nacres != 'NA', on appelle calculate_mass_based_emissions(...)
        -> (emission_mass, total_mass, emission_mass_error).
        On renvoie alors 5 valeurs :
            (emissions_price, emissions_price_error, emission_mass, emission_mass_error, total_mass).
        """
        print("Recalcul des émissions avec les données :", data)

        category = data.get('category', '')
        subcategory = data.get('subcategory', '')
        subsub_name = data.get('subsubcategory', '')
        name = data.get('name', '')
        year = data.get('year', '')

        days = data.get('days', 1)          # Nombre de jours
        value = data.get('value', 0.0)      # Par exemple euros, km, etc.
        code_nacres = data.get('code_nacres', 'NA')
        quantity = data.get('quantity', 0)

        # Variables de sortie
        emissions_price = 0.0
        emissions_price_error = 0.0
        emission_mass = 0.0
        emission_mass_error = 0.0
        total_mass = 0.0

        # --- CAS 1 : MACHINE ---
        if category == 'Machine':
            electricity_type = data.get('electricity_type', '')
            if not electricity_type:
                QMessageBox.warning(self, 'Erreur', "Type d'électricité manquant pour la machine.")
                return None, None, None, None, None

            total_usage = value  # kWh
            mask = (
                (self.data['category'] == 'Électricité') &
                (self.data['name'] == electricity_type)
            )
            filtered_data = self.data[mask]
            if filtered_data.empty:
                QMessageBox.warning(self, 'Erreur',
                                    "Impossible de trouver le facteur d'émission pour ce type d'électricité (Machine).")
                return None, None, None, None, None

            emission_factor = filtered_data['total'].values[0]
            factor_uncert = float(filtered_data.get('uncertainty', [0.0])[0])  # ex: 0.1 => ±10%

            emissions_price = total_usage * emission_factor
            emissions_price_error = emissions_price * factor_uncert

            # Pas d'émission massique => renvoie 0.0
            return emissions_price, emissions_price_error, 0.0, 0.0, 0.0

        # --- CAS 2 : AUTRES CATÉGORIES ---
        # 1) total_value
        total_value = value * days

        # 2) Chercher le facteur d’émission + incertitude
        mask = (
            (self.data['category'] == category) &
            (self.data['subcategory'] == subcategory) &
            (self.data['subsubcategory'].fillna('') == subsub_name) &
            (self.data['name'].fillna('') == name)
        )
        if year:
            mask &= (self.data['year'].astype(str) == str(year))

        filtered_data = self.data[mask]
        if filtered_data.empty:
            QMessageBox.warning(self, 'Erreur',
                                'Aucune donnée disponible pour cette sélection dans recalculate_emissions.')
            return None, None, None, None, None

        total_emission_factor = filtered_data['total'].values[0]
        factor_uncert = filtered_data.get('uncertainty', 0.0)
        if isinstance(factor_uncert, pd.Series):
            factor_uncert = factor_uncert.values[0]
        factor_uncert = float(factor_uncert) if factor_uncert else 0.0

        # 3) Calcul "emissions_price"
        emissions_price = total_value * total_emission_factor
        emissions_price_error = emissions_price * factor_uncert

        # 4) Émissions massiques (si Achats + NACRES != 'NA')
        if category == 'Achats' and code_nacres != 'NA':
            # Correction : si " - " dans code_nacres, on ne garde que la partie avant
            # exemple : "NB13 - Boite Pétri" => "NB13"
            if " - " in code_nacres:
                code_nacres = code_nacres.split(" - ", 1)[0].strip()

            emission_mass, total_mass, emission_mass_error = self.calculate_mass_based_emissions(
                code_nacres,
                quantity=quantity
            )
        else:
            emission_mass = 0.0
            emission_mass_error = 0.0
            total_mass = 0.0

        # 5) Renvoie 5 valeurs
        return emissions_price, emissions_price_error, emission_mass, emission_mass_error, total_mass
    
    def create_or_update_history_item(self, data, item=None):
        """
        Crée ou met à jour un élément dans la QListWidget d'historique.

        - Construit le texte à afficher en fonction de la catégorie 
        (Machine, Véhicules, Achats, etc.).
        - Affiche l'incertitude sous forme "± X.XXXX" si dispo.
        - Affiche également le nom du consommable le cas échéant.
        - Stocke le dictionnaire `data` dans l'UserRole de l'item.
        """
        category = data.get('category', '')
        subcategory = data.get('subcategory', '')
        subsubcategory = data.get('subsubcategory', '')
        name = data.get('name', '')
        value = data.get('value', 0)
        unit = data.get('unit', '')
        emissions_price = data.get('emissions_price', 0.0)
        emissions_price_error = data.get('emissions_price_error', 0.0)
        emission_mass = data.get('emission_mass', None)
        emission_mass_error = data.get('emission_mass_error', 0.0)
        total_mass = data.get('total_mass', None)
        code_nacres = data.get('code_nacres', 'NA')
        consommable = data.get('consommable', 'NA')

        # Petite fonction utilitaire pour afficher valeur ± incertitude
        def fmt_err(val, err):
            """Retourne 'val ± err' si err != 0, sinon juste val."""
            if err is not None and err > 0:
                return f"{val:.4f} ± {err:.4f}"
            else:
                return f"{val:.4f}"

        if category == 'Machine':
            item_text = (
                f"Machine - {subcategory} - {value:.2f} kWh : "
                f"{fmt_err(emissions_price, emissions_price_error)} kg CO₂e"
            )
        elif category == 'Véhicules':
            days = data.get('days', 1)
            total_km = data.get('value', 0.0)
            try:
                km_per_day = float(total_km) / days if days else float(total_km)
            except (ValueError, ZeroDivisionError):
                km_per_day = 0
            item_text = (
                f"{category} - {subcategory} - {code_nacres} - {name} : "
                f"{km_per_day:.2f} km/jour sur {days} jours, total {total_km} {unit} : "
                f"{fmt_err(emissions_price, emissions_price_error)} kg CO₂e"
            )
        else:
            # Exemple : Achats
            prix_str = fmt_err(emissions_price, emissions_price_error)
            item_text = (
                f"{category} - {subcategory[:12]} - {code_nacres} - {name} - "
                f"Dépense: {value} {unit} : {prix_str} kg CO₂e"
            )

            # Afficher le nom du consommable
            if consommable != 'NA':
                # On ajoute un espace ou un séparateur
                item_text += f" [Consommable: {consommable}]"

            # Si on a des émissions massiques
            if emission_mass is not None and total_mass is not None and emission_mass != 0:
                mass_str = fmt_err(emission_mass, emission_mass_error)
                item_text += f" - Masse {total_mass:.4f} kg : {mass_str} kg CO₂e"

        # Création/mise à jour de l'item
        if item:
            item.setText(item_text)
            item.setData(Qt.UserRole, data)
            return item
        else:
            from PySide6.QtWidgets import QListWidgetItem
            new_item = QListWidgetItem(item_text)
            new_item.setData(Qt.UserRole, data)
            self.history_list.addItem(new_item)
            return new_item

    def export_data(self):
        """
        Exporte les données de l'historique (self.history_list) vers un fichier (CSV, Excel ou HDF5).

        - Ouvre une boîte de dialogue pour choisir le chemin et le format.
        - Construit un DataFrame pandas à partir des items de l'historique.
        - Sauvegarde le fichier.
        """
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        import pandas as pd
        import os

        if self.history_list.count() == 0:
            QMessageBox.information(self, "Export", "L'historique est vide, rien à exporter.")
            return

        # Boîte de dialogue pour sauvegarder
        file_name, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Enregistrer l'historique",
            "",
            "Fichier CSV (*.csv);;Fichier Excel (*.xlsx);;Fichier HDF5 (*.h5);;Tous les fichiers (*)"
        )
        if not file_name:
            return  # l'utilisateur a annulé

        # Construire une liste de dictionnaires (chacune représentant un item)
        rows = []
        for i in range(self.history_list.count()):
            item = self.history_list.item(i)
            data = item.data(Qt.UserRole)
            if not data:
                continue
            rows.append(data)

        # Convertir en DataFrame
        df = pd.DataFrame(rows)

        # Vérifier l'extension du fichier
        _, extension = os.path.splitext(file_name)
        extension = extension.lower()

        try:
            if extension == '.csv':
                df.to_csv(file_name, index=False, sep=';')
            elif extension == '.xlsx':
                df.to_excel(file_name, index=False)
            elif extension == '.h5':
                df.to_hdf(file_name, key='history', mode='w')
            else:
                # Par défaut, on tente CSV
                df.to_csv(file_name, index=False, sep=';')
            QMessageBox.information(self, "Export", f"Historique exporté avec succès dans {file_name}")
        except Exception as e:
            QMessageBox.warning(self, "Erreur Export", f"Une erreur est survenue lors de l'export : {e}")

    def import_data(self):
        """
        Importe un fichier (CSV, Excel ou HDF5) contenant l'historique,
        puis recrée les items dans self.history_list.

        - Ouvre une boîte de dialogue pour sélectionner le fichier.
        - Lit le fichier dans un DataFrame pandas.
        - Convertit les colonnes clés au bon type (float/int/str).
        - Insère chaque ligne dans self.history_list sous forme d'un dictionnaire data.
        - Met à jour le total des émissions.
        """
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        import pandas as pd
        import os

        file_name, selected_filter = QFileDialog.getOpenFileName(
            self,
            "Importer l'historique",
            "",
            "Fichier CSV (*.csv);;Fichier Excel (*.xlsx);;Fichier HDF5 (*.h5);;Tous les fichiers (*)"
        )
        if not file_name:
            return  # l'utilisateur a annulé

        _, extension = os.path.splitext(file_name)
        extension = extension.lower()

        try:
            if extension == '.csv':
                # Par défaut, on suppose un séparateur ; (selon votre export)
                df = pd.read_csv(file_name, sep=';')
            elif extension == '.xlsx':
                df = pd.read_excel(file_name)
            elif extension == '.h5':
                df = pd.read_hdf(file_name, key='history')
            else:
                # Par défaut, tenter CSV
                df = pd.read_csv(file_name, sep=';')

        except Exception as e:
            QMessageBox.warning(self, "Erreur Import", f"Impossible de lire le fichier : {e}")
            return

        # -- Convertir les colonnes importantes au bon format --
        # Par exemple, si vous utilisez ces champs numériques :

        for col in ["value", "quantity", "days", "emissions_price", "emission_mass", "total_mass"]:
            if col in df.columns:
                # Convertir en numérique (entier ou float), ignorer erreurs
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # Nettoyer les colonnes textuelles (si besoin)
        for col in ["category", "subcategory", "subsubcategory", "name", "code_nacres", "consommable", "unit"]:
            if col in df.columns:
                # Enlever espaces en trop
                df[col] = df[col].astype(str).str.strip()

        # -- Ajouter chaque ligne dans l'historique --
        # On vide l'historique actuel ou on cumule (selon le comportement désiré).
        # Si vous voulez tout cumuler, ne videz pas. Sinon, faites :
        # self.history_list.clear()

        count_imported = 0
        for idx, row in df.iterrows():
            # Construire un dictionnaire similaire à ce que vous faites dans calculate_emission()
            new_data = row.to_dict()

            # Insérer dans l'historique
            self.create_or_update_history_item(new_data)
            count_imported += 1

        QMessageBox.information(self, "Import", f"{count_imported} élément(s) importé(s) depuis {file_name}.")

        # Mettre à jour le total des émissions
        self.update_total_emissions()
        self.data_changed.emit()

    def add_machine(self):
        """
        Gère l'ajout d'une machine dans l'historique (cas catégorie = 'Machine').

        - Lit la puissance (kW), le temps d'utilisation (heures/jour) et le nombre de jours.
        - Calcule total_usage (kWh) = puissance × temps × jours.
        - Récupère le facteur d'émission électrique (self.data['Électricité']).
        - Calcule les émissions totales, crée l'item d'historique et met à jour le total.
        """
        try:
            machine_name = self.machine_name_field.text().strip()
            power = float(self.power_field.text().strip())
            usage_time = float(self.usage_time_field.text().strip())
            days = int(self.days_machine_field.text().strip())

            if usage_time > 24:
                QMessageBox.warning(self, 'Erreur', "Le temps d'utilisation ne peut pas dépasser 24 heures par jour.")
                return

            total_usage = power * usage_time * days

            electricity_type = self.electricity_combo.currentText()
            mask = (self.data['category'] == 'Électricité') & (self.data['name'] == electricity_type)
            filtered_data = self.data[mask]
            if filtered_data.empty:
                QMessageBox.warning(self, 'Erreur', "Impossible de trouver le facteur d'émission pour ce type d'électricité.")
                return

            emission_factor = filtered_data['total'].values[0]
            emissions = total_usage * emission_factor

            data_for_machine = {
                'category': 'Machine',
                'subcategory': machine_name,
                'value': total_usage,
                'unit': 'kWh',
                'emissions_price': emissions,
                'power': power,
                'usage_time': usage_time,
                'days_machine': days,
                'electricity_type': electricity_type,
            }

            self.create_or_update_history_item(data_for_machine)
            self.update_total_emissions()
            self.machine_name_field.clear()
            self.power_field.clear()
            self.usage_time_field.clear()
            self.days_machine_field.clear()
            self.input_field.clear()
            self.data_changed.emit()

        except ValueError:
            QMessageBox.warning(self, 'Erreur', 'Veuillez entrer des valeurs numériques valides.')
            return

    def generate_pie_chart(self):
        """
        Ouvre ou actualise la fenêtre PieChartWindow (diagramme en secteurs).

        - Si la fenêtre n'existe pas, la crée et connecte son signal finished.
        - Sinon, appelle refresh_data().
        - Affiche la fenêtre en premier plan.
        """
        if self.pie_chart_window is None:
            self.pie_chart_window = PieChartWindow(self)
            self.pie_chart_window.finished.connect(self.on_pie_chart_window_closed)
        else:
            self.pie_chart_window.refresh_data()
        self.pie_chart_window.show()
        self.pie_chart_window.raise_()
        self.pie_chart_window.activateWindow()

    def generate_bar_chart(self):
        """
        Ouvre ou actualise la fenêtre BarChartWindow (barres empilées à 100%).

        - Même logique que generate_pie_chart, mais pour le bar chart.
        """
        if self.bar_chart_window is None:
            self.bar_chart_window = BarChartWindow(self)
            self.bar_chart_window.finished.connect(self.on_bar_chart_window_closed)
        else:
            self.bar_chart_window.refresh_data()
        self.bar_chart_window.show()
        self.bar_chart_window.raise_()
        self.bar_chart_window.activateWindow()

    def generate_proportional_bar_chart(self):
        """
        Ouvre ou actualise la fenêtre ProportionalBarChartWindow (barres empilées non normalisées).

        - Crée la fenêtre si besoin, sinon appelle refresh_data().
        - Montre la fenêtre.
        """
        if self.proportional_bar_chart_window is None:
            self.proportional_bar_chart_window = ProportionalBarChartWindow(self)
            self.proportional_bar_chart_window.finished.connect(self.on_proportional_bar_chart_window_closed)
        else:
            self.proportional_bar_chart_window.refresh_data()
        self.proportional_bar_chart_window.show()
        self.proportional_bar_chart_window.raise_()
        self.proportional_bar_chart_window.activateWindow()

    def generate_stacked_bar_consumables(self):
        """
        Ouvre ou rafraîchit la fenêtre StackedBarConsumablesWindow,
        affichant un bar chart empilé pour les consommables (Achats + 'Consommables') 
        ayant quantité > 0.

        - Si la fenêtre n'existe pas, l'instancie et connecte le signal finished.
        - Sinon, rafraîchit simplement ses données.
        - Affiche la fenêtre.
        """
        # Si la fenêtre n'existe pas encore ou a été fermée, on la recrée
        if self.stacked_bar_consumables_window is None:
            self.stacked_bar_consumables_window = StackedBarConsumablesWindow(self)
            self.stacked_bar_consumables_window.finished.connect(self.on_stacked_bar_consumables_window_closed)
        else:
            # Si elle existe déjà, on actualise juste ses données
            self.stacked_bar_consumables_window.refresh_data()

        self.stacked_bar_consumables_window.show()
        self.stacked_bar_consumables_window.raise_()
        self.stacked_bar_consumables_window.activateWindow()

    def generate_nacres_bar_chart(self):
        """
        Ouvre ou rafraîchit une fenêtre NacresBarChartWindow, 
        permettant de visualiser les émissions par code NACRES.

        - Crée la fenêtre si elle n'existe pas, sinon appelle refresh_data().
        - L'affiche et la met au premier plan.
        """
        if not hasattr(self, 'nacres_bar_chart_window') or self.nacres_bar_chart_window is None:
            # Si la fenêtre n'existe pas encore, on la crée
            self.nacres_bar_chart_window = NacresBarChartWindow(self)
            # On connecte le signal finished pour savoir quand la fenêtre se ferme
            self.nacres_bar_chart_window.finished.connect(self.on_nacres_bar_chart_window_closed)
        else:
            # Sinon, on rafraîchit juste les données
            self.nacres_bar_chart_window.refresh_data()

        self.nacres_bar_chart_window.show()
        self.nacres_bar_chart_window.raise_()
        self.nacres_bar_chart_window.activateWindow()

    def on_nacres_bar_chart_window_closed(self):
        """
        Ouvre ou rafraîchit une fenêtre NacresBarChartWindow, 
        permettant de visualiser les émissions par code NACRES.

        - Crée la fenêtre si elle n'existe pas, sinon appelle refresh_data().
        - L'affiche et la met au premier plan.
        """
        self.nacres_bar_chart_window = None

    def on_stacked_bar_consumables_window_closed(self):
        """
        Slot appelé lorsque la fenêtre StackedBarConsumablesWindow se ferme.

        - Met self.stacked_bar_consumables_window à None.
        """
        self.stacked_bar_consumables_window = None

    def on_pie_chart_window_closed(self):
        """
        Slot appelé lorsque la fenêtre StackedBarConsumablesWindow se ferme.

        - Met self.stacked_bar_consumables_window à None.
        """
        self.pie_chart_window = None

    def on_bar_chart_window_closed(self):
        """
        Slot appelé lorsque la fenêtre BarChartWindow se ferme.

        - Met self.bar_chart_window à None.
        """
        self.bar_chart_window = None

    def on_proportional_bar_chart_window_closed(self):
        """
        Slot appelé lorsque la fenêtre ProportionalBarChartWindow se ferme.

        - Met self.proportional_bar_chart_window à None.
        """
        self.proportional_bar_chart_window = None

    def open_data_mass_window(self):
        """
        Ouvre la fenêtre DataMassWindow (gestion des consommables massiques) 
        ou la met au premier plan si elle existe déjà.

        - Connecte data_mass_window.data_added à reload_data_masse.
        """
        if self.data_mass_window is None or not self.data_mass_window.isVisible():
            self.data_mass_window = DataMassWindow(parent=self, data_materials=self.data_materials)
            self.data_mass_window.data_added.connect(self.reload_data_masse)
            self.data_mass_window.show()
        else:
            self.data_mass_window.raise_()
            self.data_mass_window.activateWindow()

    def calculate_mass_based_emissions(self, code_nacres, quantity=None):
        """
        Calcule les émissions basées sur la masse (via le code NACRES et la quantité).

        - Cherche la ligne correspondante dans self.data_masse (Code NACRES + Consommable).
        - Calcule masse_totale = masse_unitaire_kg * quantité.
        - Recherche le matériau dans self.data_materials pour obtenir eCO2_par_kg + incertitude.
        - Calcule eCO2_total = masse_totale * eCO2_par_kg et l'incertitude associée.
        - Retourne (eCO2_total, masse_totale, eCO2_error).

        :param code_nacres: Le code NACRES (ex: "NB13").
        :type code_nacres: str
        :param quantity: Quantité saisie (entier). S'il est None, on lit self.quantity_input.
        :type quantity: int or None
        :return: (emission_massique, masse_totale_kg, emission_mass_error).
        :rtype: tuple(float, float, float)
        """
        # 1) Récupérer la quantité
        if quantity is None:
            try:
                quantity_str = self.quantity_input.text().strip()
                quantity = int(quantity_str) if quantity_str else 0
            except ValueError:
                quantity = 0

        # 2) Chercher la ligne correspondante dans data_masse
        #    On regarde si on a "Code NACRES" = code_nacres
        selected_nacres = self.conso_filtered_combo.currentText()
        if " - " in selected_nacres:
            code_nacres_str, objet_nom = selected_nacres.split(" - ", 1)
        else:
            code_nacres_str = code_nacres.strip()
            objet_nom = ""

        matching = self.data_masse[
            (self.data_masse['Code NACRES'].str.strip() == code_nacres_str) &
            (self.data_masse["Consommable"].str.strip() == objet_nom)
        ]

        if matching.empty:
            return 0.0, 0.0, 0.0  # pas trouvé => pas d'émission

        row = matching.iloc[0]
        masse_g = row.get("Masse unitaire (g)", 0.0)
        materiau = row.get("Matériau", "")
        # Ici, on lit la colonne "incertitude" massique :
        incert_mass_factor = row.get("uncertainty", 0.0)  # ex. 0.1 => ±10%

        # 3) Calcul de la masse totale
        masse_kg_unitaire = float(masse_g) / 1000.0
        masse_totale_kg = masse_kg_unitaire * quantity

        # 4) Chercher le facteur CO₂ du matériau dans data_materials
        mat_filter = self.data_materials[self.data_materials['Materiau'] == materiau]
        if mat_filter.empty:
            return 0.0, masse_totale_kg, 0.0

        eCO2_par_kg = float(mat_filter.iloc[0].get("Equivalent CO₂ (kg eCO₂/kg)", 0.0))
        # Incertitude du matériau (si vous l'avez dans data_materials) :
        incert_material = float(mat_filter.iloc[0].get("uncertainty", 0.0))  # ex. 0.05 => ±5%

        # 5) Calcul final
        eCO2_total = masse_totale_kg * eCO2_par_kg

        # 6) Combiner incertitude massique + incertitude matériau
        #    => On suppose indépendance => incert_total = sqrt((incert_mass_factor^2) + (incert_material^2))
        #    => Erreur absolue = eCO2_total * incert_total
        incert_total_fraction = (incert_mass_factor**2 + incert_material**2)**0.5
        eCO2_total_error = eCO2_total * incert_total_fraction

        return eCO2_total, masse_totale_kg, eCO2_total_error

    def update_nacres_visibility(self):
        """
        Affiche ou masque la zone "Consommable" et sa barre de recherche 
        en fonction de la catégorie et de la sous-catégorie sélectionnées.

        - Si category == "Achats" et subcategory contient "Consommables", 
          on rend la zone visible et on appelle self.update_conso_filtered_combo().
        - Sinon, on masque tout (label, combo, search, quantité).
        """
        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        
        # Critère : Achats + sous-catégorie contenant 'Consommables'
        if category == 'Achats' and 'Consommables' in subcategory:
            self.conso_filtered_label.setVisible(True)
            self.conso_filtered_combo.setVisible(True)
            self.conso_search_label.setVisible(True)
            self.conso_search_field.setVisible(True)
            # Optionnel : mettre à jour la combo NACRES
            self.update_conso_filtered_combo()
        else:
            self.conso_filtered_label.setVisible(False)
            self.conso_filtered_combo.setVisible(False)
            self.conso_search_label.setVisible(False)
            self.conso_search_field.setVisible(False)
            self.quantity_label.setVisible(False)    # On masque aussi la quantité
            self.quantity_input.setVisible(False)

    def show_sources_popup(self, link_str):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton

        dialog = QDialog(self)
        dialog.setWindowTitle("Sources")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        sources_text = """
        <p><b>Sources et Références :</b></p>
        <ul>
            <li>
                <b><a href="https://base-empreinte.ademe.fr/">Base Carbone®</a></b><br>
                Source officielle pour les données de l'ADEME (Agence de la Transition Écologique).
            </li>
            <li>
                <b><a href="https://labos1point5.org/">Labo 1point5</a></b><br>
                Plateforme collaborative pour la réduction de l'empreinte carbone dans les laboratoires de recherche.
            </li>
            <li>
                <b><a href="https://plasticseurope.org/fr/">PlasticsEurope</a></b><br>
                Organisation représentant les fabricants de plastiques en Europe, fournissant des données sur l'industrie.
            </li>
            <li>
                <b><a href="https://www.oecd.org/fr/data/">OCDE</a></b><br>
                Organisation de Coopération et de Développement Économiques, base de données sur les indicateurs environnementaux.
            </li>
            <li>
                <b><a href="https://440megatonnes.ca/fr/insight/mesurer-lempreinte-carbone-du-plastique/">440 Megatonnes</a></b><br>
                Analyse des impacts carbone du plastique.
            </li>
            <li>
                <b><a href="https://www.ansell.com/-/media/projects/ansell/website/pdf/industrial/safety-briefing-blogs/emea/reducing-the-impact-of-disposable-glove-manufacturing-on-the-environment/safety-briefing_reducing-the-impact-of-disposable-glove-manufacturing-on-the-environment_en.ashx?rev=96e1cea169c54f0b995d5a4c1f2876d0">Ansell - Reducing the impact of disposable glove manufacturing on the environment</a></b><br>
                Article d'Ansell discutant des mesures pour réduire l'impact environnemental de la fabrication des gants jetables.
            </li>
        </ul>

        <p><b>Articles Scientifiques :</b></p>
        <ul>
            <li>
                <b><em>Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consumables</em></b><br>
                Isabella Ragazzi, publié dans <b><a href="https://doi.org/10.1371/journal.pstr.0000080">PLOS</a></b>, septembre 2023.<br>
                DOI : <a href="https://doi.org/10.1371/journal.pstr.0000080">10.1371/journal.pstr.0000080</a>.
            </li>
            <li>
                <b><em>The environmental impact of personal protective equipment in the UK healthcare system</em></b><br>
                Reed, S. et al., publié dans <b><a href="https://journals.sagepub.com/doi/epub/10.1177/01410768211001583">Journal of the Royal Society of Medicine</a></b>, 2021.<br>
                DOI : <a href="https://journals.sagepub.com/doi/epub/10.1177/01410768211001583">10.1177/01410768211001583</a>.
            </li>
        </ul>
        """
        label = QLabel()
        label.setTextFormat(Qt.RichText)
        label.setOpenExternalLinks(True)
        label.setText(sources_text)
        layout.addWidget(label)

        close_button = QPushButton("Fermer")
        close_button.clicked.connect(dialog.close)
        layout.addWidget(close_button)

        dialog.setLayout(layout)
        dialog.exec()