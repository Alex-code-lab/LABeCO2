# windows/main_window.py

import sys
import os
import pandas as pd
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QComboBox, QLineEdit,
    QListWidget, QMessageBox, QVBoxLayout, QHBoxLayout, QWidget,
    QInputDialog, QFormLayout, QFileDialog,
    QListWidgetItem, QScrollArea
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from utils.data_loader import load_data, load_logo, resource_path
from windows.pie_chart import PieChartWindow
from windows.bar_chart import BarChartWindow
from windows.proportional_bar_chart import ProportionalBarChartWindow
from windows.data_mass_window import DataMassWindow  # Import de DataMassWindow


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
        data_masse_path = os.path.join(base_path, 'data_masse_eCO2', 'data_eCO2_masse_consommable.hdf5')
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
        # Assurez-vous que 'Materiau' et 'eCO2_kg' existent dans self.data_materials

        # Initialisation de variables
        self.calculs = []
        self.calcul_data = []
        self.current_unit = None
        self.total_emissions = 0.0

        # Fenêtres complémentaires
        self.pie_chart_window = None
        self.bar_chart_window = None
        self.proportional_bar_chart_window = None
        self.data_mass_window = None # Important: initialisation à None

        # Widgets principaux
        # ComboBox pour sélectionner la catégorie principale (ex : Achats, Véhicules, Machines, etc.).
        self.category_combo = None  
        # ComboBox pour sélectionner la sous-catégorie associée à la catégorie choisie (ex : "Consommables" pour "Achats").
        self.subcategory_combo = None  
        # ComboBox pour sélectionner une sous-sous-catégorie ou un nom spécifique dans la sous-catégorie choisie.
        self.subsub_name_combo = None  
        # ComboBox pour choisir l'année des données utilisées pour les calculs (ex : année d'achat ou de référence).
        self.year_combo = None  
        # Champ de saisie (QLineEdit) pour entrer une valeur numérique pour le calcul des émissions (ex : quantité, valeur monétaire).
        self.input_field = None  
        # Champ de saisie pour indiquer le nombre de jours d'utilisation dans des catégories spécifiques (ex : Véhicules, Machines).
        self.days_field = None  
        # Groupe de widgets (QWidget) dédié à la gestion des informations pour les "Machines" (nom, puissance, etc.).
        self.machine_group = None  
        # Liste (QListWidget) pour afficher l'historique des calculs effectués par l'utilisateur.
        self.history_list = None  
        # Label pour afficher le total des émissions calculées (ex : "Total des émissions : 0.0000 kg CO₂e").
        self.result_area = None  
        # Champ de recherche (QLineEdit) pour filtrer ou rechercher des éléments dans les sous-catégories.
        self.search_field = None  
        # Label pour afficher le logo de l'application en haut de l'interface.
        self.logo_label = None  
        # Label pour afficher du texte d'introduction ou d'information dans la partie "header" (ex : contexte, objectifs de l'application).
        self.header_label = None  
        # Label indiquant le texte de l'instruction pour l'utilisateur (ex : "Entrez la valeur en kg").
        self.input_label = None  
        # Label indiquant le texte pour le nombre de jours d'utilisation (visible uniquement pour certaines catégories).
        self.days_label = None  

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
        self.resize(600, 700)
        screen = QApplication.primaryScreen()
        screen_size = screen.size()
        self.setMaximumSize(screen_size.width(), screen_size.height())
        self.setMinimumSize(600, 700)

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
        """
        self.category_label = QLabel('Catégorie:')
        self.category_combo = QComboBox()

        categories = self.data['category'].dropna().unique().tolist()
        categories = [cat for cat in categories if cat != 'Électricité']
        categories.append('Machine')
        self.category_combo.addItems(sorted(categories))

        self.subcategory_label = QLabel('Sous-catégorie:')
        self.subcategory_combo = QComboBox()

        self.search_label = QLabel('Rechercher:')
        self.search_field = QLineEdit()

        self.subsub_name_label = QLabel('Sous-sous-catégorie - Nom:')
        self.subsub_name_combo = QComboBox()

        self.year_label = QLabel('Année:')
        self.year_combo = QComboBox()

        self.input_label = QLabel('Entrez la valeur:')
        self.input_field = QLineEdit()
        self.input_field.setEnabled(False)

        self.days_label = QLabel("Nombre de jours d'utilisation:")
        self.days_field = QLineEdit()
        self.days_field.setEnabled(False)
        self.days_label.setVisible(False)
        self.days_field.setVisible(False)

        self.calculate_button = QPushButton('Calculer le Bilan Carbone')
        self.calculate_button.setToolTip("Calcule le bilan carbone sélectionné et tente également le calcul via la masse si possible.")
        # self.calculate_button.clicked.connect(self.calculate_emission)

        existing_layout = QVBoxLayout()
        existing_layout.setSpacing(5)
        existing_layout.addWidget(self.category_label)
        existing_layout.addWidget(self.category_combo)
        existing_layout.addWidget(self.subcategory_label)
        existing_layout.addWidget(self.subcategory_combo)
        existing_layout.addWidget(self.search_label)
        existing_layout.addWidget(self.search_field)
        existing_layout.addWidget(self.subsub_name_label)
        existing_layout.addWidget(self.subsub_name_combo)
        existing_layout.addWidget(self.year_label)
        existing_layout.addWidget(self.year_combo)

        # NACRES filtré
        self.nacres_filtered_label = QLabel("Code NACRES Filtré :")
        self.nacres_filtered_combo = QComboBox()
        self.nacres_filtered_label.setVisible(False)
        self.nacres_filtered_combo.setVisible(False)
        existing_layout.addWidget(self.nacres_filtered_label)
        existing_layout.addWidget(self.nacres_filtered_combo)

        # Ajout du champ quantité
        self.quantity_label = QLabel("Quantité:")
        self.quantity_input = QLineEdit()
        self.quantity_label.setVisible(False)
        self.quantity_input.setVisible(False)

        existing_layout.addWidget(self.quantity_label)
        existing_layout.addWidget(self.quantity_input)

         # Bouton Gestion des Consommables
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
        existing_layout.addWidget(self.manage_consumables_button)

        existing_layout.addWidget(self.input_label)
        existing_layout.addWidget(self.input_field)
        existing_layout.addWidget(self.days_label)
        existing_layout.addWidget(self.days_field)
        existing_layout.addWidget(self.calculate_button)

        existing_group = QWidget()
        existing_group.setLayout(existing_layout)
        main_layout.addWidget(existing_group)

    def initUIMachineSection(self, main_layout):
        """
        Initialise la partie spécifique pour l'ajout d'une "Machine"
        """
        self.machine_name_label = QLabel('Nom de la machine:')
        self.machine_name_field = QLineEdit()
        self.power_label = QLabel('Puissance de la machine (kW):')
        self.power_field = QLineEdit()
        self.usage_time_label = QLabel("Temps d'utilisation par jour (heures):")
        self.usage_time_field = QLineEdit()
        self.days_machine_label = QLabel("Nombre de jours d'utilisation:")
        self.days_machine_field = QLineEdit()
        self.electricity_label = QLabel('Type d\'électricité:')
        self.electricity_combo = QComboBox()

        electricity_types = self.data[self.data['category'] == 'Électricité']['name'].dropna().unique()
        self.electricity_combo.addItems(sorted(electricity_types))

        self.add_machine_button = QPushButton('Ajouter la machine')
        self.add_machine_button.clicked.connect(self.add_machine)

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
        self.delete_button.clicked.connect(self.delete_selected_calculation)
        self.modify_button = QPushButton('Modifier le calcul sélectionné')
        self.modify_button.clicked.connect(self.modify_selected_calculation)

        calc_buttons_layout = QHBoxLayout()
        calc_buttons_layout.setSpacing(1)
        calc_buttons_layout.addWidget(self.delete_button)
        calc_buttons_layout.addWidget(self.modify_button)

        self.export_button = QPushButton('Exporter les données')
        self.export_button.clicked.connect(self.export_data)
        self.import_button = QPushButton('Importer les données')
        self.import_button.clicked.connect(self.import_data)

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
        self.generate_pie_button.clicked.connect(self.generate_pie_chart)
        self.generate_pie_button.setToolTip("Affiche un diagramme en secteurs...")

        self.generate_bar_button = QPushButton('Barres Empilées à 100%')
        self.generate_bar_button.clicked.connect(self.generate_bar_chart)
        self.generate_bar_button.setToolTip("Affiche un graphique à barres empilées à 100%...")

        self.generate_proportional_bar_button = QPushButton('Barres Empilées')
        self.generate_proportional_bar_button.clicked.connect(self.generate_proportional_bar_chart)
        self.generate_proportional_bar_button.setToolTip("Affiche un graphique à barres empilées proportionnelles...")

        buttons_layout_graph = QHBoxLayout()
        buttons_layout_graph.addWidget(self.generate_pie_button)
        buttons_layout_graph.addWidget(self.generate_bar_button)
        buttons_layout_graph.addWidget(self.generate_proportional_bar_button)
        main_layout.addLayout(buttons_layout_graph)
        main_layout.addSpacing(5)

    def initUISignals(self):
        """
        Connexion des signaux/slots
        """
        # Gère le clic sur le lien dans le header pour afficher/masquer le texte complet.
        self.header_label.linkActivated.connect(self.toggle_text_display)

        # Met à jour les sous-catégories lorsqu'une catégorie est sélectionnée.
        self.category_combo.currentIndexChanged.connect(self.update_subcategories)

        # Met à jour les sous-sous-catégories lorsqu'une sous-catégorie est sélectionnée.
        self.subcategory_combo.currentIndexChanged.connect(self.update_subsubcategory_names)

        # Met à jour les sous-sous-catégories lorsqu'un texte est saisi dans le champ de recherche.
        self.search_field.textChanged.connect(self.update_subsubcategory_names)

        # Met à jour les années disponibles lorsqu'une sous-sous-catégorie est sélectionnée.
        self.subsub_name_combo.currentIndexChanged.connect(self.update_years)

        # Met à jour l'unité d'entrée lorsque l'année sélectionnée change.
        self.year_combo.currentIndexChanged.connect(self.update_unit)

        # Met à jour les options filtrées des codes NACRES lorsque l'année sélectionnée change.
        self.year_combo.currentIndexChanged.connect(self.update_nacres_filtered_combo)

        # Ouvre l'interface pour modifier un calcul lorsqu'un élément de l'historique est double-cliqué.
        self.history_list.itemDoubleClicked.connect(self.modify_calculation)

        # Lance le calcul des émissions lorsqu'on clique sur le bouton "Calculer".
        self.calculate_button.clicked.connect(self.calculate_emission)

        # Ajoute une machine avec ses paramètres lorsqu'on clique sur "Ajouter la machine".
        self.add_machine_button.clicked.connect(self.add_machine)

        # Supprime le calcul sélectionné dans l'historique lorsqu'on clique sur "Supprimer".
        self.delete_button.clicked.connect(self.delete_selected_calculation)

        # Ouvre l'interface pour modifier un calcul lorsqu'on clique sur "Modifier".
        self.modify_button.clicked.connect(self.modify_selected_calculation)

        # Exporte les données dans un fichier lorsqu'on clique sur "Exporter".
        self.export_button.clicked.connect(self.export_data)

        # Importe des données depuis un fichier lorsqu'on clique sur "Importer".
        self.import_button.clicked.connect(self.import_data)

        # Affiche un diagramme en secteurs (camembert) lorsqu'on clique sur "Diagramme en Secteurs".
        self.generate_pie_button.clicked.connect(self.generate_pie_chart)

        # Affiche un graphique à barres empilées à 100% lorsqu'on clique sur "Barres Empilées à 100%".
        self.generate_bar_button.clicked.connect(self.generate_bar_chart)

        # Affiche un graphique à barres empilées proportionnelles lorsqu'on clique sur "Barres Empilées".
        self.generate_proportional_bar_button.clicked.connect(self.generate_proportional_bar_chart)
            
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

    def update_subcategories(self):
        category = self.category_combo.currentText()
        if category == 'Machine':
            self.subcategory_label.setVisible(False)
            self.subcategory_combo.setVisible(False)
            self.search_label.setVisible(False)
            self.search_field.setVisible(False)
            self.subsub_name_label.setVisible(False)
            self.subsub_name_combo.setVisible(False)
            self.year_label.setVisible(False)
            self.year_combo.setVisible(False)
            self.input_label.setVisible(False)
            self.input_field.setVisible(False)
            self.days_label.setVisible(False)
            self.days_field.setVisible(False)
            self.calculate_button.setVisible(False)
            self.machine_group.setVisible(True)

            self.nacres_filtered_label.setVisible(False)
            self.nacres_filtered_combo.setVisible(False)
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)
        else:
            self.subcategory_label.setVisible(True)
            self.subcategory_combo.setVisible(True)
            self.search_label.setVisible(True)
            self.search_field.setVisible(True)
            self.subsub_name_label.setVisible(True)
            self.subsub_name_combo.setVisible(True)
            self.year_label.setVisible(True)
            self.year_combo.setVisible(True)
            self.input_label.setVisible(True)
            self.input_field.setVisible(True)
            self.calculate_button.setVisible(True)
            self.machine_group.setVisible(False)

            subcategories = self.data[self.data['category'] == category]['subcategory'].dropna().unique()
            self.subcategory_combo.clear()
            self.subcategory_combo.addItems(sorted(subcategories.astype(str)))
            self.update_subsubcategory_names()

            if category == "Véhicules":
                self.days_label.setVisible(True)
                self.days_field.setVisible(True)
                self.days_field.setEnabled(True)
            else:
                self.days_label.setVisible(False)
                self.days_field.setVisible(False)
                self.days_field.setEnabled(False)

    def update_subsubcategory_names(self):
        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        search_text = self.search_field.text().lower()
        mask = (self.data['category'] == category) & (self.data['subcategory'] == subcategory)
        filtered_data = self.data[mask]
        subsub_names = (filtered_data['subsubcategory'].fillna('') + ' - ' + filtered_data['name'].fillna('')).str.strip(' - ')
        subsub_names_unique = subsub_names.unique()

        if search_text:
            subsub_names_filtered = [s for s in subsub_names_unique if search_text in s.lower()]
        else:
            subsub_names_filtered = subsub_names_unique

        self.subsub_name_combo.clear()
        self.subsub_name_combo.addItems(sorted(subsub_names_filtered))
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
        self.year_combo.clear()
        self.year_combo.addItems(sorted(years))
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

    def update_nacres_filtered_combo(self):
        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        subsub_name = self.subsub_name_combo.currentText()

        if category == 'Achats' and 'Consommables' in subcategory:
            self.nacres_filtered_label.setVisible(True)
            self.nacres_filtered_combo.setVisible(True)
            self.nacres_filtered_combo.clear()

            if subsub_name:
                subsubcategory, name = self.split_subsub_name(subsub_name)
                code_nacres_prefix = subsubcategory[:4]
                filtered_entries = self.data_masse[
                    self.data_masse['Code NACRES'].str.strip().str.startswith(code_nacres_prefix, na=False)
                ]

                if not filtered_entries.empty:
                    for idx, row in filtered_entries.iterrows():
                        nom_objet_val = row["Nom de l'objet"]
                        display_text = f"{row['Code NACRES']} - {nom_objet_val}"
                        self.nacres_filtered_combo.addItem(display_text)

            # Toujours ajouter "Aucune correspondance"
            self.nacres_filtered_combo.addItem("Aucune correspondance")
            self.nacres_filtered_combo.setCurrentText("Aucune correspondance")

            self.nacres_filtered_combo.currentIndexChanged.connect(self.on_nacres_filtered_changed)

        else:
            self.nacres_filtered_label.setVisible(False)
            self.nacres_filtered_combo.setVisible(False)
            self.nacres_filtered_combo.clear()
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)

    def on_nacres_filtered_changed(self):
        selected_text = self.nacres_filtered_combo.currentText()
        if selected_text == "Aucune correspondance":
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)
        else:
            self.quantity_label.setVisible(True)
            self.quantity_input.setVisible(True)

    def split_subsub_name(self, subsub_name):
        if ' - ' in subsub_name:
            subsubcategory, name = subsub_name.split(' - ', 1)
        else:
            subsubcategory = ''
            name = subsub_name
        return subsubcategory.strip(), name.strip()

    def calculate_emission(self):
        print("calculate_emission appelé")
        category = self.category_combo.currentText()

        # Cas "Machine"
        if category == 'Machine':
            self.add_machine()
            self.input_field.clear()
            self.update_total_emissions()
            self.data_changed.emit()
            return
        else:
            # Récupération de la sélection "Code NACRES filtré"
            selected_nacres = self.nacres_filtered_combo.currentText() if self.nacres_filtered_combo.isVisible() else None
            # On vérifie si la sélection NACRES est "Aucune correspondance" ou non
            has_nacres_match = (selected_nacres and selected_nacres != "Aucune correspondance")

            # Lecture de la valeur entrée par l'utilisateur
            try:
                input_text = self.input_field.text().strip()  # Suppression des espaces
                print(f"Debug: Input text = '{input_text}'")  # Vérifiez ce qui est réellement dans input_field
                value = float(input_text)
                print(f"Debug: Value = {value}")
                if value < 0:
                    QMessageBox.warning(self, 'Erreur', 'La valeur doit être positive.')
                    return
            except ValueError as e:
                print(f"Debug: ValueError - {e}")
                QMessageBox.warning(self, 'Erreur', 'Veuillez entrer une valeur numérique positive valide.')
                return

            # Récupération du nombre de jours si c'est pour les véhicules (ou autre caté qui l'exige)
            days = int(self.days_field.text()) if self.days_field.isEnabled() and self.days_field.text() else 1
            total_value = value * days

            subcategory = self.subcategory_combo.currentText()
            subsub_name = self.subsub_name_combo.currentText()
            year = self.year_combo.currentText()
            subsubcategory, name = self.split_subsub_name(subsub_name)

            # Filtrage des données pour le calcul principal (basé sur le prix)
            mask = (
                (self.data['category'] == category) &
                (self.data['subcategory'] == subcategory) &
                (self.data['subsubcategory'].fillna('') == subsubcategory) &
                (self.data['name'].fillna('') == name) &
                (self.data['year'].astype(str) == year)
            )

            filtered_data = self.data[mask]
            if filtered_data.empty:
                self.result_area.setText('Aucune donnée disponible pour cette sélection.')
                return

            total_emission_factor = filtered_data['total'].values[0]
            emissions = total_value * total_emission_factor

            # Construction du texte de base (toujours le calcul basé sur le prix)
            item_text = f'{category} - {subcategory} - {subsub_name} - {total_value} {self.current_unit} : {emissions:.4f} kg CO₂e'

            # Maintenant on gère l'affichage concernant la partie "masse"
            # Pour l'instant, le calcul via la masse n'est pas encore implémenté, 
            # donc on se limite à "calcul à venir" si on a une correspondance NACRES, 
            # sinon "pas de données".
            if has_nacres_match:
                # NACRES filtré sélectionné et différent de "Aucune correspondance"
                # Affichage "calcul à venir"
                item_text += " - calcul à venir"
            else:
                # Soit pas de NACRES ou "Aucune correspondance"
                item_text += " - pas de données"

            # Ajout dans l'historique
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, {
                'category': category,
                'subcategory': subcategory,
                'subsubcategory': subsubcategory,
                'name': name,
                'value': total_value,
                'unit': self.current_unit,
                'emissions': emissions
            })

            # Vérification que l'item n'existe pas déjà dans l'historique (optionnel)
            existing_items = [self.history_list.item(i).text() for i in range(self.history_list.count())]
            if item_text not in existing_items:
                self.history_list.addItem(item)

            self.update_total_emissions()
            self.input_field.clear()
            self.data_changed.emit()
        
    def update_total_emissions(self):
        total_emissions = 0.0
        for i in range(self.history_list.count()):
            item = self.history_list.item(i)
            data = item.data(Qt.UserRole)
            if data:
                emissions = data.get('emissions', 0)
                total_emissions += emissions
        self.total_emissions = total_emissions
        self.result_area.setText(f'Total des émissions : {total_emissions:.4f} kg CO₂e')

    def delete_selected_calculation(self):
        selected_row = self.history_list.currentRow()
        if selected_row >= 0:
            self.history_list.takeItem(selected_row)
            self.update_total_emissions()
            self.data_changed.emit()

    def modify_selected_calculation(self):
        selected_item = self.history_list.currentItem()
        if selected_item:
            self.modify_calculation(selected_item)
        else:
            QMessageBox.warning(self, 'Erreur', 'Veuillez sélectionner un calcul à modifier.')

    def modify_calculation(self, item):
        selected_row = self.history_list.row(item)
        if selected_row < 0:
            QMessageBox.warning(self, 'Erreur', 'Veuillez sélectionner un calcul à modifier.')
            return

        data = item.data(Qt.UserRole)
        if not data:
            QMessageBox.warning(self, 'Erreur', 'Données de calcul manquantes.')
            return

        category = data.get('category', '')
        subcategory = data.get('subcategory', '')
        subsubcategory = data.get('subsubcategory', '')
        name = data.get('name', '')
        unit = data.get('unit', '')
        current_value = data.get('value', 0)
        emissions = data.get('emissions', 0)
        days = data.get('days', 1)  # Par défaut, 1 si non défini

        summary = f"{category}\n{subcategory}\n{subsubcategory}\n{name}"
        QMessageBox.information(self, 'Modifier le Calcul', f"Résumé des Catégories :\n\n{summary}")

        new_value, ok = QInputDialog.getDouble(
            self,
            'Nouvelle Valeur',
            f'Entrez la nouvelle valeur en {unit}:',
            value=current_value,
            decimals=5,
        )
        if ok and new_value < 0:
            QMessageBox.warning(self, "Valeur invalide", "La valeur doit être positive.")
            return

        if not ok:
            return

        if category in ['Véhicules', 'Machine', 'Activités agricoles', 'Infra. de recherche']:
            new_days, ok_days = QInputDialog.getInt(
                self,
                'Nombre de Jours',
                'Entrez le nouveau nombre de jours d\'utilisation:',
                value=days,
            )
            if ok_days and new_days < 0:
                QMessageBox.warning(self, "Valeur invalide", "La valeur doit être positive.")
                return

            if not ok_days:
                return
        else:
            new_days = days

        # Recalculer les émissions
        if category == 'Machine':
            total_value = new_value * new_days
            electricity_type = self.electricity_combo.currentText()
            mask = (self.data['category'] == 'Électricité') & (self.data['name'] == electricity_type)
            filtered_data = self.data[mask]
            if not filtered_data.empty:
                emission_factor = filtered_data['total'].values[0]
            else:
                QMessageBox.warning(self, 'Erreur', 'Impossible de trouver le facteur d\'émission pour le type d\'électricité sélectionné.')
                return
            new_emissions = total_value * emission_factor

        elif category == 'Véhicules':
            total_value = new_value * new_days
            mask = (self.data['category'] == 'Véhicules') & (self.data['subcategory'] == subcategory)
            filtered_data = self.data[mask]
            if not filtered_data.empty:
                emission_factor = filtered_data['total'].values[0]
            else:
                QMessageBox.warning(self, 'Erreur', 'Impossible de trouver le facteur d\'émission pour le véhicule sélectionné.')
                return
            new_emissions = total_value * emission_factor

        elif category == 'Achats':
            total_value = new_value
            mask = (
                (self.data['category'] == 'Achats') &
                (self.data['subcategory'] == subcategory) &
                (self.data['subsubcategory'].fillna('') == subsubcategory) &
                (self.data['name'].fillna('') == name)
            )
            filtered_data = self.data[mask]
            if not filtered_data.empty:
                emission_factor = filtered_data['total'].values[0]
            else:
                QMessageBox.warning(self, 'Erreur', 'Impossible de trouver le facteur d\'émission pour cet achat.')
                return
            new_emissions = total_value * emission_factor

        elif category == 'Activités agricoles':
            total_value = new_value * new_days
            mask = (
                (self.data['category'] == 'Activités agricoles') &
                (self.data['subcategory'] == subcategory) &
                (self.data['subsubcategory'].fillna('') == subsubcategory) &
                (self.data['name'].fillna('') == name)
            )
            filtered_data = self.data[mask]
            if not filtered_data.empty:
                emission_factor = filtered_data['total'].values[0]
            else:
                QMessageBox.warning(self, 'Erreur', 'Impossible de trouver le facteur d\'émission pour cette activité agricole.')
                return
            new_emissions = total_value * emission_factor

        elif category == 'Infra. de recherche':
            total_value = new_value * new_days
            mask = (
                (self.data['category'] == 'Infra. de recherche') &
                (self.data['subcategory'] == subcategory) &
                (self.data['subsubcategory'].fillna('') == subsubcategory) &
                (self.data['name'].fillna('') == name)
            )
            filtered_data = self.data[mask]
            if not filtered_data.empty:
                emission_factor = filtered_data['total'].values[0]
            else:
                QMessageBox.warning(self, 'Erreur', 'Impossible de trouver le facteur d\'émission pour cette infrastructure de recherche.')
                return
            new_emissions = total_value * emission_factor

        else:
            QMessageBox.warning(self, 'Erreur', f'Catégorie non gérée : {category}')
            return

        data['value'] = new_value
        data['emissions'] = new_emissions
        if category in ['Véhicules', 'Machine', 'Activités agricoles', 'Infra. de recherche']:
            data['days'] = new_days

        item.setData(Qt.UserRole, data)

        if category == 'Machine':
            item_text = f'Machine - {subcategory} - {total_value:.2f} kWh : {new_emissions:.4f} kg CO₂e'
        elif category == 'Véhicules':
            item_text = f'Vehicules - {subcategory} - {total_value:.2f} : {new_emissions:.4f} kg CO₂e'
        elif category == 'Achats':
            item_text = f'Achats - {subcategory} - {subsubcategory} - {name} - {total_value:.2f} {unit} : {new_emissions:.4f} kg CO₂e'
        elif category == 'Activités agricoles':
            item_text = f'Activités agricoles - {subcategory} - {subsubcategory} - {name} - {total_value:.5f} {unit} : {new_emissions:.5f} kg CO₂e'
        elif category == 'Infra. de recherche':
            item_text = f'Infra. de recherche - {subcategory} - {subsubcategory} - {name} - {total_value:.5f} {unit} : {new_emissions:.5f} kg CO₂e'
        else:
            item_text = f'{category} - {subcategory} - {subsubcategory} - {name} - {total_value:.5f} {unit} : {new_emissions:.5f} kg CO₂e'

        item.setText(item_text)

        self.update_total_emissions()
        self.data_changed.emit()

        QMessageBox.information(self, 'Succès', 'Calcul modifié avec succès.')

    def export_data(self):
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
                    'Émissions (kg CO₂e)': data.get('emissions', 0)
                })

        df = pd.DataFrame(data_to_export)
        if df.empty:
            QMessageBox.information(self, 'Information', 'Aucune donnée valide à exporter.')
            return

        default_file_name = os.path.join(os.getcwd(), 'bilan_carbone_export.csv')
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter les données",
            default_file_name,
            "Fichiers CSV (*.csv);;Tous les fichiers (*)",
            options=options
        )

        if file_name:
            if not file_name.endswith('.csv'):
                file_name += '.csv'
            try:
                df.to_csv(file_name, index=False, encoding='utf-8-sig')
                QMessageBox.information(self, 'Succès', f'Données exportées avec succès dans {file_name}')
            except Exception as e:
                QMessageBox.warning(self, 'Erreur', f'Une erreur est survenue lors de l\'exportation : {e}')
        else:
            QMessageBox.information(self, 'Annulation', 'Exportation annulée.')

    def import_data(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(self, "Importer les données", "", "Fichiers CSV (*.csv);;Tous les fichiers (*)", options=options)
        if file_name:
            try:
                df = pd.read_csv(file_name)
                required_columns = {'Catégorie', 'Sous-catégorie', 'Valeur', 'Émissions (kg CO₂e)'}
                if not required_columns.issubset(df.columns):
                    QMessageBox.warning(self, 'Erreur', 'Le fichier CSV ne contient pas les colonnes nécessaires.')
                    return

                for index, row in df.iterrows():
                    category = row.get('Catégorie', '')
                    subcategory = row.get('Sous-catégorie', '')
                    subsubcategory = row.get('Sous-sous-catégorie', '')
                    name = row.get('Nom', '')
                    value = row.get('Valeur', 0)
                    unit = row.get('Unité', '')
                    emissions = row.get('Émissions (kg CO₂e)', 0)

                    if category == 'Machine':
                        item_text = f'Machine - {subcategory} - {value:.2f} {unit} : {emissions:.4f} kg CO₂e'
                    else:
                        subsub_name = f'{subsubcategory} - {name}' if subsubcategory else name
                        item_text = f'{category} - {subcategory} - {subsub_name} - {value} {unit} : {emissions:.4f} kg CO₂e'

                    item = QListWidgetItem(item_text)
                    item.setData(Qt.UserRole, {
                        'category': category,
                        'subcategory': subcategory,
                        'subsubcategory': subsubcategory,
                        'name': name,
                        'value': value,
                        'unit': unit,
                        'emissions': emissions
                    })
                    self.history_list.addItem(item)

                self.update_total_emissions()
                QMessageBox.information(self, 'Succès', 'Données importées avec succès.')
                self.data_changed.emit()
            except Exception as e:
                QMessageBox.warning(self, 'Erreur', f'Erreur lors de l\'importation : {e}')

    def add_machine(self):
        try:
            machine_name = self.machine_name_field.text()
            power = float(self.power_field.text())
            usage_time = float(self.usage_time_field.text())
            days = int(self.days_machine_field.text())
            total_usage = power * usage_time * days

            electricity_type = self.electricity_combo.currentText()
            mask = (self.data['category'] == 'Électricité') & (self.data['name'] == electricity_type)
            filtered_data = self.data[mask]
            if not filtered_data.empty:
                emission_factor = filtered_data['total'].values[0]
            else:
                QMessageBox.warning(self, 'Erreur', 'Impossible de trouver le facteur d\'émission pour ce type d\'électricité.')
                return

            emissions = total_usage * emission_factor
            item_text = f'Machine - {machine_name} - {total_usage:.2f} kWh : {emissions:.4f} kg CO₂e'
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, {
                'category': 'Machine',
                'subcategory': machine_name,
                'value': total_usage,
                'unit': 'kWh',
                'emissions': emissions
            })
            self.history_list.addItem(item)

            self.update_total_emissions()
            self.machine_name_field.clear()
            self.power_field.clear()
            self.usage_time_field.clear()
            self.days_machine_field.clear()
            self.input_field.clear()
            self.data_changed.emit()
        except ValueError:
            QMessageBox.warning(self, 'Erreur', 'Veuillez entrer des valeurs numériques valides.')
        self.update_total_emissions()
        self.data_changed.emit()

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
            self.update_nacres_filtered_combo()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors du rechargement des données massiques : {e}")

    def calculer_eCO2_via_masse(self):
        # Vérifier si nacres_filtered_combo est sur "Aucune correspondance"
        if self.nacres_filtered_combo.currentText() == "Aucune correspondance":
            # On pourrait soit ne pas calculer, soit calculer quand même selon le besoin
            QMessageBox.information(self, 'Information', 
                                    'Vous avez sélectionné "Aucune correspondance", le calcul se fera quand même.')
            # Si vous voulez calculer quand même, poursuivez. Sinon return.

        # Récupérer la quantité
        try:
            quantite = int(self.quantity_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Erreur", "La quantité doit être un entier valide.")
            return

        if quantite <= 0:
            QMessageBox.warning(self, "Erreur", "La quantité doit être positive.")
            return

        # Récupérer les infos sur le consommable depuis nacres_filtered_combo
        # Par exemple, si le texte est "NB13 - Tube Falcon 15ml"
        selected_text = self.nacres_filtered_combo.currentText()
        if " - " in selected_text:
            code_nacres, objet_nom = selected_text.split(" - ", 1)
        else:
            # Si aucun tiret, peut-être "Aucune correspondance"
            code_nacres = selected_text
            objet_nom = "Inconnu"

        # Trouver l'entrée correspondante dans data_masse
        matching = self.data_masse[self.data_masse['Code NACRES'].str.strip() == code_nacres.strip()]
        if matching.empty:
            QMessageBox.warning(self, "Erreur", "Aucun consommable trouvé pour ce code NACRES.")
            return

        last_obj = matching.iloc[0]
        masse_g = last_obj["Masse unitaire (g)"]
        materiau = last_obj["Matériau"]

        if self.data_materials is None:
            QMessageBox.warning(self, "Erreur", "Les données matériaux ne sont pas chargées.")
            return

        masse_kg = masse_g / 1000.0
        mat_filter = self.data_materials[self.data_materials['Materiau'] == materiau]
        if mat_filter.empty:
            QMessageBox.warning(self, "Erreur", f"Matériau '{materiau}' non trouvé dans data_materials.")
            return

        eCO2_par_kg = mat_filter['eCO2_kg'].values[0]
        eCO2_total = quantite * masse_kg * eCO2_par_kg

        QMessageBox.information(self, "Calcul eCO₂ via masse",
                                f"Consommable: {objet_nom}\n"
                                f"Quantité: {quantite}\n"
                                f"Masse unitaire: {masse_g} g ({masse_kg:.4f} kg)\n"
                                f"Matériau: {materiau}\n"
                                f"eCO₂ par kg matériau: {eCO2_par_kg:.4f} kg CO₂e/kg\n"
                                f"eCO₂ total: {eCO2_total:.4f} kg CO₂e"
                            )