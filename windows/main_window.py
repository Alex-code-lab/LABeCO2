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
    """
    data_changed = Signal()

    def __init__(self):
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
        data_masse_path = os.path.join(base_path, 'data_masse_eCO2', 'mock_consumables_100.hdf5')#'data_eCO2_masse_consommable.hdf5')
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
        Initialise l'interface utilisateur.
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

        self.source_label = QLabel(
            'Les données utilisées ici sont issues de la base de données fournie par <a href="https://labos1point5.org/" style="color:blue; text-decoration:none;">Labo 1point5</a>'
        )
        self.source_label.setOpenExternalLinks(True)
        self.source_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.source_label)

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
        Initialise la partie haute de l'interface.
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
        Initialise la partie sélection de catégorie, sous-catégorie, etc.
        avec des champs alignés.
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
        Initialise la partie spécifique pour l'ajout d'une "Machine"
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
        Initialise la partie Historique des calculs
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
        Initialise la zone avec les boutons pour générer les graphiques.
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
        Connexion des signaux/slots
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
        Se déclenche à chaque modification du champ de recherche.
        On met à jour subsubcategory + NACRES, puis on tente de sélectionner
        automatiquement l'élément s'il n'y a qu'une seule correspondance.
        """
        self.update_subsubcategory_names()
        self.update_conso_filtered_combo(filter_text=None)
        self.synchronize_after_search()

    def synchronize_after_search(self):
        """
        Si, après la recherche, il n'y a qu'une seule correspondance (outre "non renseignée")
        dans subsub_name_combo ou conso_filtered_combo, on la sélectionne automatiquement.
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
        category = self.category_combo.currentText()
        if category == 'Machine':
            # Masquer la zone "Achats/Véhicules/etc." pour Machine
            self.subcategory_label.setVisible(False)
            self.subcategory_combo.setVisible(False)
            self.search_label.setVisible(False)
            self.search_field.setVisible(False)
            self.subsub_name_label.setVisible(False)
            self.subsub_name_combo.setVisible(False)
            # self.year_label.setVisible(False)
            self.year_combo.setVisible(False)
            self.input_label.setVisible(False)
            self.input_field.setVisible(False)
            self.days_label.setVisible(False)
            self.days_field.setVisible(False)
            self.calculate_button.setVisible(False)
            self.machine_group.setVisible(True)
            self.machine_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            self.manage_consumables_button.setVisible(False)

            # Pour Machine, rendre NACRES visible mais la vider
            self.conso_filtered_label.setVisible(True)
            self.conso_filtered_combo.setVisible(True)
            self.conso_filtered_combo.clear()
            self.conso_filtered_combo.addItem("non renseignée")
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)
        else:
            # Réafficher les éléments pour les autres catégories
            self.subcategory_label.setVisible(True)
            self.subcategory_combo.setVisible(True)
            self.search_label.setVisible(True)
            self.search_field.setVisible(True)
            self.subsub_name_label.setVisible(True)
            self.subsub_name_combo.setVisible(True)
            # self.year_label.setVisible(True)
            self.year_combo.setVisible(True)
            self.input_label.setVisible(True)
            self.input_field.setVisible(True)
            self.calculate_button.setVisible(True)
            self.machine_group.setVisible(False)
            self.machine_group.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            self.manage_consumables_button.setVisible(True)

            # Mise à jour de la combo sous-catégories
            subcategories = self.data[self.data['category'] == category]['subcategory'].dropna().unique()
            self.subcategory_combo.clear()
            self.subcategory_combo.addItems(sorted(subcategories.astype(str)))
            self.update_subsubcategory_names()
            self.update_nacres_visibility()

            # Gestion spécifique pour "Véhicules"
            if category == "Véhicules":
                self.days_label.setVisible(True)
                self.days_field.setVisible(True)
                self.days_field.setEnabled(True)
            else:
                self.days_label.setVisible(False)
                self.days_field.setVisible(False)
                self.days_field.setEnabled(False)

        # Gestion de l'affichage Conso selon la catégorie
        # if category == 'Achats':
        #     # Afficher et mettre à jour la section NACRES pour Achats
        #     self.conso_filtered_label.setVisible(True)
        #     self.conso_filtered_combo.setVisible(True)
        #     self.update_conso_filtered_combo()
        # else:
        #     # Masquer la section NACRES pour les autres catégories
        #     self.conso_filtered_label.setVisible(False)
        #     self.conso_filtered_combo.setVisible(False)
        #     self.quantity_label.setVisible(False)
        #     self.quantity_input.setVisible(False)

        # # On force la mise à jour NACRES dans tous les cas
        # self.update_nacres_filtered_combo()

    def update_subsubcategory_names(self):
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
        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        subsub_name = self.subsub_name_combo.currentText()
        year = self.year_combo.currentText()
        subsubcategory, name = self.split_subsub_name(subsub_name)

        mask = (
            (self.data['category'] == category) &
            (self.data['subcategory'] == subcategory) &
            (self.data['subsubcategory'].fillna('') == subsubcategory) &
            (self.data['name'].fillna('') == name) &
            (self.data['year'].astype(str) == year)
        )

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
        Met à jour la liste déroulante NACRES/Consommable en fonction d'un texte de recherche.
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
        Lorsqu'une sous-sous-catégorie est sélectionnée,
        on récupère le code NACRES (les 4 premiers caractères du subsubcategory)
        et on ne garde dans la combo NACRES que les consommables qui correspondent.
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
        Lorsqu'on sélectionne un consommable NACRES dans conso_filtered_combo :
        - Si "non renseignée", on masque quantité et on désactive la valeur en euro.
        - Sinon, on force la catégorie "Achats" + sous-catégorie "Consommables(...)",
        on met à jour la combo subsub_name, et on tente de sélectionner la bonne
        sous-sous-catégorie via subsubcategory[:4] == code_nacres_4.
        - Enfin, on appelle update_unit() pour activer le champ euro si la ligne existe.
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
        Montre ou cache le champ 'quantité' selon si on a sélectionné un consommable
        spécifique (≠ 'non renseignée') dans la combo NACRES.
        """
        current_nacres = self.conso_filtered_combo.currentText()
        if (not current_nacres) or (current_nacres == "non renseignée"):
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)
        else:
            self.quantity_label.setVisible(True)
            self.quantity_input.setVisible(True)

    def add_logo(self):
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
        if self.header_label.text() == self.collapsed_text:
            self.header_label.setText(self.full_text)
        else:
            self.header_label.setText(self.collapsed_text)

    def split_subsub_name(self, subsub_name):
        if ' - ' in subsub_name:
            subsubcategory, name = subsub_name.split(' - ', 1)
        else:
            subsubcategory = ''
            name = subsub_name
        return subsubcategory.strip(), name.strip()

    def calculate_emission(self):
        """
        Calcule les émissions carbone en fonction des données saisies et sélectionnées par l'utilisateur.
        Ajoute également les informations NACRES (si disponibles) dans l'historique.
        """
        print("calculate_emission appelé")

        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        subsub_name = self.subsub_name_combo.currentText()
        year = self.year_combo.currentText()
        subsubcategory, category_nacres = self.split_subsub_name(subsub_name)

        # Cas spécial : Machine
        if category == 'Machine':
            self.add_machine()
            self.input_field.clear()
            self.update_total_emissions()
            self.data_changed.emit()
            return

        # Code NACRES par défaut
        code_nacres = 'NA'
        consommable = 'NA'

        # Si "Achats" et on a subsubcategory
        if category == 'Achats' and subsubcategory:
            code_nacres = subsubcategory[:4]

        # Récup combo NACRES
        selected_nacres = (
            self.conso_filtered_combo.currentText()
            if self.conso_filtered_combo.isVisible()
            else None
        )
        has_nacres_match = selected_nacres and selected_nacres != "non renseignée"
        if has_nacres_match:
            if " - " in selected_nacres:
                code_nacres, consommable = selected_nacres.split(" - ", 1)

        # Récup la valeur
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

        # Recherche du facteur d’émission dans self.data
        mask = (
            (self.data['category'] == category) &
            (self.data['subcategory'] == subcategory) &
            (self.data['subsubcategory'].fillna('') == subsubcategory) &
            (self.data['name'].fillna('') == category_nacres) &
            (self.data['year'].astype(str) == year)
        )
        filtered_data = self.data[mask]
        if filtered_data.empty:
            self.result_area.setText('Aucune donnée disponible pour cette sélection.')
            return

        total_emission_factor = filtered_data['total'].values[0]
        emissions = total_value * total_emission_factor

        # Récupérer la quantité seulement si le champ est visible
        quantity = 0
        if self.quantity_label.isVisible() and self.quantity_input.isVisible():
            try:
                quantity_str = self.quantity_input.text().strip()
                quantity = int(quantity_str) if quantity_str else 0
            except:
                quantity = 0

        # Gestion des émissions massiques via NACRES
        emission_massique, total_mass = None, None
        if has_nacres_match:
            emission_massique, total_mass = self.calculate_mass_based_emissions(code_nacres)

        new_data = {
            'category': category,
            'subcategory': subcategory,
            'subsubcategory': subsubcategory,
            'name': category_nacres,
            'value': total_value,
            'unit': self.current_unit,
            'emissions_price': emissions,
            'emission_mass': emission_massique if emission_massique is not None else None,
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
        total_emissions = 0.0
        total_mass_emissions_conso = 0.0
        total_price_emissions_conso = 0.0

        for i in range(self.history_list.count()):
            item = self.history_list.item(i)
            data = item.data(Qt.UserRole)
            if data:
                emissions_price = data.get('emissions_price', data.get('emissions', 0))
                total_emissions += emissions_price

                emission_mass = data.get('emission_mass', 0)
                if emission_mass is None or emission_mass == 'NA':
                    emission_mass = 0.0
                else:
                    total_price_emissions_conso += emissions_price
                    total_mass_emissions_conso += float(emission_mass)

        self.total_emissions = total_emissions
        self.total_mass_emissions_conso = total_mass_emissions_conso
        self.total_price_emissions_conso = total_price_emissions_conso
        self.result_area.setText(
            f'Total des émissions (prix) : {total_emissions:.4f} kg CO₂e\n'
            f'Emission des consommables par la masse : {total_mass_emissions_conso:.4f} kg CO₂e\n'
            f'Emission des consommables par le prix : {total_price_emissions_conso:.4f} kg CO₂e'
        )

    def delete_selected_calculation(self):
        selected_row = self.history_list.currentRow()
        if selected_row >= 0:
            self.history_list.takeItem(selected_row)
            self.update_total_emissions()
            self.data_changed.emit()

    def modify_selected_calculation(self):
        selected_item = self.history_list.currentItem()
        if not selected_item:
            QMessageBox.warning(self, 'Erreur', 'Veuillez sélectionner un calcul à modifier.')
            return

        data = selected_item.data(Qt.UserRole)
        if not data:
            QMessageBox.warning(self, 'Erreur', 'Aucune donnée disponible pour cet élément.')
            return

        dialog = EditCalculationDialog(
            parent=self,
            data=data,
            main_data=self.data,
            data_masse=self.data_masse,
            data_materials=self.data_materials
        )
        if dialog.exec() == QDialog.Accepted:
            modified_data = dialog.modified_data
            emissions, emission_massique, total_mass = self.recalculate_emissions(modified_data)
            modified_data['emissions_price'] = emissions
            modified_data['emission_mass'] = emission_massique
            modified_data['total_mass'] = total_mass

            self.history_list.takeItem(self.history_list.row(selected_item))
            self.create_or_update_history_item(modified_data)
            self.update_total_emissions()

        self.data_changed.emit()

    def recalculate_emissions(self, data):
        """
        Recalcule les émissions carbone en fonction des données fournies.
        """
        print("Recalcul des émissions avec les données :", data)

        category = data.get('category', '')
        if category == 'Machine':
            # Cas Machine
            machine_name = data.get('subcategory', '')
            total_usage = data.get('value', 0.0)
            electricity_type = data.get('electricity_type', '')
            if not electricity_type:
                QMessageBox.warning(self, 'Erreur', "Type d'électricité manquant pour la machine.")
                return None, None, None

            mask = (self.data['category'] == 'Électricité') & (self.data['name'] == electricity_type)
            filtered_data = self.data[mask]
            if filtered_data.empty:
                QMessageBox.warning(self, 'Erreur', "Impossible de trouver le facteur d'émission pour ce type d'électricité.")
                return None, None, None

            emission_factor = filtered_data['total'].values[0]
            emissions = total_usage * emission_factor
            return emissions, None, None

        # Autres catégories
        subcategory = data.get('subcategory', '')
        subsub_name = data.get('subsubcategory', '')
        name = data.get('name', '')
        year = data.get('year', '')
        value = data.get('value', 0)

        mask = (
            (self.data['category'] == category) &
            (self.data['subcategory'] == subcategory) &
            (self.data['subsubcategory'].fillna('') == subsub_name) &
            (self.data['name'].fillna('') == name) &
            (self.data['year'].astype(str) == str(year))
        )
        filtered_data = self.data[mask]
        if filtered_data.empty:
            QMessageBox.warning(self, 'Erreur', 'Aucune donnée disponible pour cette sélection.')
            return None, None, None

        total_emission_factor = filtered_data['total'].values[0]
        emissions = float(value) * float(total_emission_factor)

        code_nacres = data.get('code_nacres', 'NA')
        emission_massique, total_mass = None, None
        if category == 'Achats' and code_nacres != 'NA':
            quantity = data.get('quantity', 1)
            emission_massique, total_mass = self.calculate_mass_based_emissions(code_nacres, quantity=quantity)

        return emissions, emission_massique, total_mass

    def create_or_update_history_item(self, data, item=None):
        """
        Crée ou met à jour un élément dans l'historique avec les données fournies.
        """
        category = data.get('category', '')
        subcategory = data.get('subcategory', '')
        subsubcategory = data.get('subsubcategory', '')
        name = data.get('name', '')
        value = data.get('value', 0)
        unit = data.get('unit', '')
        emissions_price = data.get('emissions_price', data.get('emissions', 0)) or 0
        emission_mass = data.get('emission_mass', None)
        total_mass = data.get('total_mass', None)
        code_nacres = data.get('code_nacres', 'NA')
        consommable = data.get('consommable', 'NA')

        if category == 'Machine':
            item_text = (
                f"Machine - {subcategory} - {value:.2f} kWh : "
                f"{emissions_price:.4f} kg CO₂e"
            )
        elif category == 'Véhicules':
            days = data.get('days', 1)
            total_km = data.get('value', 0)
            try:
                km_per_day = float(total_km) / days if days else float(total_km)
            except (ValueError, ZeroDivisionError):
                km_per_day = 0
            item_text = (
                f"{category} - {subcategory} - {code_nacres} - {name} : "
                f"{km_per_day:.2f} km/jour sur {days} jours, total {total_km} {unit} : "
                f"{emissions_price:.4f} kg CO₂e"
            )
        else:
            item_text = (
                f"{category} - {subcategory[:12]} - {code_nacres} - {name} - "
                f"Dépense: {value} {unit} : {emissions_price:.4f} kg CO₂e"
            )

            if emission_mass is not None and total_mass is not None:
                item_text += f" - Masse {total_mass:.4f} kg : {emission_mass:.4f} kg CO₂e"
            elif consommable != 'NA':
                item_text += f" - Consommable: {consommable}"
            else:
                item_text += " - Pas de précisions."

        if item:
            item.setText(item_text)
            item.setData(Qt.UserRole, data)
            return item
        else:
            new_item = QListWidgetItem(item_text)
            new_item.setData(Qt.UserRole, data)
            self.history_list.addItem(new_item)
            return new_item

    def export_data(self):
        """
        Exporte les données de l'historique dans un fichier (CSV, Excel ou HDF5).
        """
        if self.history_list.count() == 0:
            QMessageBox.information(self, 'Information', 'Aucune donnée à exporter.')
            return

        data_to_export = []
        for i in range(self.history_list.count()):
            item = self.history_list.item(i)
            data = item.data(Qt.UserRole)
            if data:
                data_to_export.append({
                    'Catégorie': data.get('category', ''),
                    'Sous-catégorie': data.get('subcategory', ''),
                    'Sous-sous-catégorie': data.get('subsubcategory', ''),
                    'Nom': data.get('name', ''),
                    'Valeur': data.get('value', 0),
                    'Unité': data.get('unit', ''),
                    'Émissions (kg CO₂e)': data.get('emissions_price', 0),
                    'Code NACRES': data.get('code_nacres', 'NA'),
                    'Consommable': data.get('consommable', 'NA')
                })

        df = pd.DataFrame(data_to_export)
        if df.empty:
            QMessageBox.information(self, 'Information', 'Aucune donnée valide à exporter.')
            return

        default_file_name = os.path.join(os.getcwd(), 'bilan_carbone_export')
        options = QFileDialog.Options()
        file_name, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Exporter les données",
            default_file_name,
            "Fichiers CSV (*.csv);;Fichiers Excel (*.xlsx);;Fichiers HDF5 (*.h5);;Tous les fichiers (*)",
            options=options
        )

        if not file_name:
            QMessageBox.information(self, 'Annulation', 'Exportation annulée.')
            return

        # Ajout extension si besoin
        if selected_filter == "Fichiers CSV (*.csv)" and not file_name.endswith('.csv'):
            file_name += '.csv'
        elif selected_filter == "Fichiers Excel (*.xlsx)" and not file_name.endswith('.xlsx'):
            file_name += '.xlsx'
        elif selected_filter == "Fichiers HDF5 (*.h5)" and not file_name.endswith('.h5'):
            file_name += '.h5'

        try:
            if file_name.endswith('.csv'):
                df.to_csv(file_name, index=False, encoding='utf-8-sig')
            elif file_name.endswith('.xlsx'):
                df.to_excel(file_name, index=False, engine='openpyxl')
            elif file_name.endswith('.h5'):
                df.to_hdf(file_name, key='bilan_carbone', mode='w')
            QMessageBox.information(self, 'Succès', f'Données exportées avec succès dans {file_name}')
        except Exception as e:
            QMessageBox.warning(self, 'Erreur', f'Une erreur est survenue lors de l\'exportation : {e}')

    def import_data(self):
        """
        Importe les données à partir d'un fichier (CSV, Excel ou HDF5) et les ajoute à l'historique.
        """
        print("Début de la méthode d'importation")

        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Importer les données",
            "",
            "Fichiers supportés (*.csv *.xlsx *.h5);;Tous les fichiers (*)",
            options=options
        )

        if not file_name:
            print("Aucun fichier sélectionné")
            return

        try:
            if file_name.endswith('.csv'):
                df = pd.read_csv(file_name)
            elif file_name.endswith('.xlsx'):
                df = pd.read_excel(file_name, engine='openpyxl')
            elif file_name.endswith('.h5'):
                df = pd.read_hdf(file_name, key='bilan_carbone')
            else:
                QMessageBox.warning(self, 'Erreur', 'Type de fichier non pris en charge.')
                return

            required_columns = {'Catégorie', 'Sous-catégorie', 'Valeur', 'Émissions (kg CO₂e)', 'Code NACRES', 'Consommable'}
            if not required_columns.issubset(df.columns):
                QMessageBox.warning(self, 'Erreur', 'Le fichier importé ne contient pas les colonnes nécessaires.')
                return

            for index, row in df.iterrows():
                category = row.get('Catégorie', '')
                subcategory = row.get('Sous-catégorie', '')
                subsubcategory = row.get('Sous-sous-catégorie', '')
                name = row.get('Nom', '')
                value = row.get('Valeur', 0)
                unit = row.get('Unité', '')
                emissions = row.get('Émissions (kg CO₂e)', 0)
                code_nacres = row.get('Code NACRES', 'NA')
                consommable = row.get('Consommable', 'NA')

                if category == 'Machine':
                    item_text = f'Machine - {subcategory} - {value:.2f} {unit} : {emissions:.4f} kg CO₂e'
                else:
                    subsub_name = f'{subsubcategory} - {name}' if subsubcategory else name
                    item_text = f'{category} - {subcategory} - {subsub_name} - {value} {unit} : {emissions:.4f} kg CO₂e'
                    if code_nacres != 'NA':
                        item_text += f" - Code NACRES: {code_nacres}"
                    if consommable != 'NA':
                        item_text += f" - Consommable: {consommable}"

                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, {
                    'category': category,
                    'subcategory': subcategory,
                    'subsubcategory': subsubcategory,
                    'name': name,
                    'value': value,
                    'unit': unit,
                    'emissions': emissions,
                    'code_nacres': code_nacres,
                    'consommable': consommable
                })
                self.history_list.addItem(item)

            self.update_total_emissions()
            print("Fin de l'importation")
            QMessageBox.information(self, 'Succès', 'Données importées avec succès.')
            self.data_changed.emit()

        except Exception as e:
            QMessageBox.warning(self, 'Erreur', f'Erreur lors de la lecture du fichier : {e}')

    def add_machine(self):
        """
        Gère l'ajout d'une machine dans l'historique, 
        en calculant son Bilan Carbone selon la puissance, le temps d'usage, etc.
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
        if self.pie_chart_window is None:
            self.pie_chart_window = PieChartWindow(self)
            self.pie_chart_window.finished.connect(self.on_pie_chart_window_closed)
        else:
            self.pie_chart_window.refresh_data()
        self.pie_chart_window.show()
        self.pie_chart_window.raise_()
        self.pie_chart_window.activateWindow()

    def generate_bar_chart(self):
        if self.bar_chart_window is None:
            self.bar_chart_window = BarChartWindow(self)
            self.bar_chart_window.finished.connect(self.on_bar_chart_window_closed)
        else:
            self.bar_chart_window.refresh_data()
        self.bar_chart_window.show()
        self.bar_chart_window.raise_()
        self.bar_chart_window.activateWindow()

    def generate_proportional_bar_chart(self):
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
        Ouvre (ou rafraîchit) la fenêtre StackedBarConsumablesWindow,
        qui affiche un graphique de barres empilées pour
        les consommables (Achats + 'Consommables') ayant quantité > 0.
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
        Ouvre (ou rafraîchit) une fenêtre affichant un Bar Chart dédié à l'analyse 
        par code NACRES, regroupant et/ou empilant les émissions. 
        Vous pouvez adapter la logique interne selon vos besoins (filtrage, etc.).
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
        Slot appelé quand la fenêtre NacresBarChartWindow se ferme.
        Permet de remettre l'attribut nacres_bar_chart_window à None
        pour pouvoir la recréer plus tard.
        """
        self.nacres_bar_chart_window = None

    def on_stacked_bar_consumables_window_closed(self):
        """
        Slot appelé quand la fenêtre de barres empilées se ferme.
        On met l'attribut à None pour pouvoir la recréer plus tard.
        """
        self.stacked_bar_consumables_window = None

    def on_pie_chart_window_closed(self):
        self.pie_chart_window = None

    def on_bar_chart_window_closed(self):
        self.bar_chart_window = None

    def on_proportional_bar_chart_window_closed(self):
        self.proportional_bar_chart_window = None

    def open_data_mass_window(self):
        if self.data_mass_window is None or not self.data_mass_window.isVisible():
            self.data_mass_window = DataMassWindow(parent=self, data_materials=self.data_materials)
            self.data_mass_window.data_added.connect(self.reload_data_masse)
            self.data_mass_window.show()
        else:
            self.data_mass_window.raise_()
            self.data_mass_window.activateWindow()

    def reload_data_masse(self):
        """
        Recharge les données massiques après l'ajout d'un nouveau consommable.
        """
        data_masse_path = resource_path(os.path.join('data_masse_eCO2', 'data_eCO2_masse_consommable.hdf5'))
        try:
            self.data_masse = pd.read_hdf(data_masse_path)
            QMessageBox.information(self, "Succès", "Données massiques rechargées avec succès.")
            self.update_conso_filtered_combo()
            # Optionnel : on peut ajouter un item "Aucune correspondance" si besoin
            # self.nacres_filtered_combo.insertItem(0, "Aucune correspondance")

        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors du rechargement des données massiques : {e}")

    def calculate_mass_based_emissions(self, code_nacres, quantity=None):
        """
        Calcule les émissions massiques basées sur le code NACRES et la quantité.
        """
        if quantity is None:
            quantite_text = self.quantity_input.text().strip()
            if not quantite_text:
                return 0, 0
            try:
                quantity = int(quantite_text)
                if quantity <= 0:
                    raise ValueError("La quantité doit être un entier positif.")
                print(f"Debug: Quantité saisie = '{quantity}'")
            except ValueError as e:
                QMessageBox.warning(self, "Erreur", str(e))
                return None, None
        else:
            try:
                quantity = int(quantity)
                if quantity <= 0:
                    raise ValueError("La quantité doit être un entier positif.")
                print(f"Debug: Quantité fournie = '{quantity}'")
            except ValueError as e:
                QMessageBox.warning(self, "Erreur", str(e))
                return None, None

        selected_nacres = self.conso_filtered_combo.currentText()
        if " - " in selected_nacres:
            code_nacres_str, objet_nom = selected_nacres.split(" - ", 1)
        else:
            code_nacres_str = selected_nacres.strip()
            objet_nom = ""

        matching = self.data_masse[
            (self.data_masse['Code NACRES'].str.strip() == code_nacres_str) &
            (self.data_masse["Consommable"].str.strip() == objet_nom)
        ]

        if matching.empty:
            QMessageBox.warning(self, "Erreur", f"Aucun consommable trouvé pour le code NACRES: {code_nacres_str} et l'objet: {objet_nom}")
            return None, None

        consommable_row = matching.iloc[0]
        masse_g = consommable_row["Masse unitaire (g)"]
        materiau = consommable_row["Matériau"]

        masse_kg_unitaire = masse_g / 1000.0
        masse_totale_kg = masse_kg_unitaire * quantity

        mat_filter = self.data_materials[self.data_materials['Materiau'] == materiau]
        if mat_filter.empty:
            QMessageBox.warning(self, "Erreur", f"Matériau '{materiau}' non trouvé dans les données de matériaux.")
            return None, None

        eCO2_par_kg = float(mat_filter.iloc[0]["Equivalent CO₂ (kg eCO₂/kg)"])
        eCO2_total = masse_totale_kg * eCO2_par_kg

        return eCO2_total, masse_totale_kg
    
    def update_nacres_visibility(self):
        """
        Affiche ou masque la ligne 'Consommable' + 'Rechercher Consommable'
        uniquement si :
            - la catégorie est 'Achats'
            - la sous-catégorie contient le mot 'Consommables'
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