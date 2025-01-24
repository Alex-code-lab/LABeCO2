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

# On importe DataManager et CarbonCalculator
from windows.data_manager import DataManager
from windows.carbon_calculator import CarbonCalculator

from utils.data_loader import load_logo, resource_path
from windows.graphiques.pie_chart import PieChartWindow
from windows.graphiques.bar_chart import BarChartWindow
from windows.graphiques.proportional_bar_chart import ProportionalBarChartWindow
from windows.data_mass_window import DataMassWindow
from windows.edit_calculation_dialog import EditCalculationDialog
from windows.graphiques.stacked_bar_consumables import StackedBarConsumablesWindow
from windows.graphiques.nacres_bar_chart import NacresBarChartWindow
from windows.graphiques.proportional_bar_chart_mass import ProportionalBarChartNacresWindow

class MainWindow(QMainWindow):
    data_changed = Signal()

    def __init__(self):
        """
        Initialise la fenêtre principale du calculateur de bilan carbone LABeCO₂.

        Configure le titre de la fenêtre, initialise les gestionnaires de données, charge les données,
        configure le CarbonCalculator, et initialise les composants de l'interface utilisateur ainsi que les signaux.
        """
        super().__init__()
        self.setWindowTitle("LABeCO₂ - Calculateur de Bilan Carbone")

        # 1) DataManager
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(".")

        try:
            self.data_manager = DataManager(base_path)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger les données : {e}")
            sys.exit(1)

        # 2) Récup DataFrame
        self.data = self.data_manager.get_main_data()
        self.data_masse = self.data_manager.get_data_masse()
        self.data_materials = self.data_manager.get_data_materials()

        # 3) CarbonCalculator
        self.carbon_calculator = CarbonCalculator(self.data_manager)

        # Variables
        self.calculs = []
        self.calcul_data = []
        self.current_unit = None
        self.total_emissions = 0.0

        # Fenêtres graphiques
        self.pie_chart_window = None
        self.bar_chart_window = None
        self.proportional_bar_chart_window = None
        self.data_mass_window = None
        self.stacked_bar_consumables_window = None
        self.nacres_bar_chart_window = None

        # Widgets
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

        # NACRES
        self.conso_filtered_label = None
        self.conso_filtered_combo = None
        self.quantity_label = None
        self.quantity_input = None

        self.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #a9a9a9;
                border-radius: 4px;
                padding: 2px 8px;
                font: system;
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
        Initialise l'interface utilisateur principale.

        Organise les différents layouts, sections et widgets de l'application,
        configure les éléments graphiques et prépare la fenêtre principale pour l'affichage.
        """
        main_layout = QVBoxLayout()
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.initUIHeader(main_layout)
        self.initUICategorySelectors(main_layout)
        self.initUIMachineSection(main_layout)
        self.initUIHistory(main_layout)
        self.initUIGraphButtons(main_layout)

        # Label de résultat
        self.result_area = QLabel("Total des émissions : 0.0000 kg CO₂e")
        main_layout.addWidget(self.result_area)

        # Label des sources
        self.sources_label = QLabel("L&#39;ensemble des sources sont à retrouver <a href=\"#\">ici</a>.")
        self.sources_label.setTextFormat(Qt.RichText)
        self.sources_label.setOpenExternalLinks(False)
        self.sources_label.setTextInteractionFlags(Qt.TextBrowserInteraction | Qt.LinksAccessibleByMouse)
        self.sources_label.setAlignment(Qt.AlignCenter)
        self.sources_label.linkActivated.connect(self.show_sources_popup)
        main_layout.addWidget(self.sources_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        container = QWidget()
        container.setLayout(main_layout)
        scroll_area.setWidget(container)
        self.setCentralWidget(scroll_area)

        self.initUISignals()
        self.update_subcategories()

        self.resize(760, 700)
        screen = QApplication.primaryScreen()
        screen_size = screen.size()
        self.setMaximumSize(screen_size.width(), screen_size.height())
        self.setMinimumSize(700, 700)

    def initUIHeader(self, main_layout):
        """
        Initialise la section d'en-tête de l'interface utilisateur.

        Ajoute le logo de l'application et configure le texte d'introduction avec une option pour afficher
        plus ou moins de contenu. Intègre également des liens interactifs pour accéder à des informations supplémentaires.
        
        Args:
            main_layout (QVBoxLayout): Le layout principal auquel ajouter les éléments de l'en-tête.
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

    def add_logo(self):
        """
        Ajoute le logo de l'application à l'en-tête.

        Charge l'image du logo, la redimensionne de manière proportionnelle,
        et l'affiche dans un QLabel aligné au centre. En cas d'échec du chargement, affiche un message d'erreur.
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
        Bascule l'affichage du texte d'introduction entre l'état développé et réduit.

        Permet à l'utilisateur de voir plus ou moins de contenu dans la section d'en-tête en cliquant sur un lien.
        """
        if self.header_label.text() == self.collapsed_text:
            self.header_label.setText(self.full_text)
        else:
            self.header_label.setText(self.collapsed_text)

    def initUICategorySelectors(self, main_layout):
        """
        Initialise les sélecteurs de catégories dans l'interface utilisateur.

        Configure les labels, comboboxes et champs de saisie pour la sélection des catégories,
        sous-catégories, noms, années, consommables, et les champs d'entrée des valeurs.
        Ajoute également les boutons pour calculer, gérer les consommables, et les actions d'import/export.
        
        Args:
            main_layout (QVBoxLayout): Le layout principal auquel ajouter les sélecteurs de catégories.
        """
        # Label + ComboBox catégorie
        self.category_label = QLabel('Catégorie:')
        self.category_combo = QComboBox()
        categories = self.data['category'].dropna().unique().tolist()
        # Éviter 'Électricité' ici
        categories = [cat for cat in categories if cat != 'Électricité']
        categories.append('Machine')
        self.category_combo.addItems(sorted(categories))

        # Sous-catégorie
        self.subcategory_label = QLabel('Sous-catégorie:')
        self.subcategory_combo = QComboBox()

        # Nom (subsub_name) + barre de recherche
        self.subsub_name_label = QLabel('Nom:')
        self.subsub_name_combo = QComboBox()
        self.subsub_name_combo.setFixedWidth(200)
        self.search_label = QLabel('Recherche:')
        self.search_field = QLineEdit()
        self.search_field.setFixedWidth(200)

        nom_layout = QHBoxLayout()
        nom_layout.addWidget(self.subsub_name_combo)
        nom_layout.addWidget(self.search_label)
        nom_layout.addWidget(self.search_field)

        # NACRES / consommable
        self.conso_filtered_label = QLabel("Consommable:")
        self.conso_filtered_combo = QComboBox()
        self.conso_filtered_combo.setFixedWidth(200)
        self.conso_search_label = QLabel("Recherche:")
        self.conso_search_field = QLineEdit()
        self.conso_search_field.setFixedWidth(200)

        conso_layout = QHBoxLayout()
        conso_layout.addWidget(self.conso_filtered_combo)
        conso_layout.addWidget(self.conso_search_label)
        conso_layout.addWidget(self.conso_search_field)

        self.year_combo = QComboBox(parent=self)
        self.year_combo.setVisible(False)

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

        self.input_label = QLabel('Entrez la valeur:')
        self.input_field = QLineEdit()
        self.input_field.setEnabled(False)

        self.days_label = QLabel("Nombre de jours d'utilisation:")
        self.days_field = QLineEdit()
        self.days_field.setEnabled(False)
        self.days_label.setVisible(False)
        self.days_field.setVisible(False)

        self.calculate_button = QPushButton('Calculer le Bilan Carbone')

        form_layout = QFormLayout()
        form_layout.setSpacing(5)
        form_layout.setLabelAlignment(Qt.AlignRight)

        form_layout.addRow(self.category_label, self.category_combo)
        form_layout.addRow(self.subcategory_label, self.subcategory_combo)
        form_layout.addRow(self.subsub_name_label, nom_layout)
        form_layout.addRow(self.conso_filtered_label, conso_layout)

        existing_layout = QVBoxLayout()
        existing_layout.setSpacing(5)
        existing_layout.addLayout(form_layout)
        existing_layout.addWidget(self.quantity_label)
        existing_layout.addWidget(self.quantity_input)
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
        Initialise la section dédiée aux machines dans l'interface utilisateur.

        Configure les champs de saisie pour les informations des machines (nom, puissance, temps d'utilisation, nombre de jours, type d'électricité)
        et le bouton pour ajouter une machine au calculateur.
        
        Args:
            main_layout (QVBoxLayout): Le layout principal auquel ajouter la section des machines.
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
        # Récupérer la liste de name pour la catégorie Électricité
        mask_elec = self.data['category'] == 'Électricité'
        electricity_types = self.data[mask_elec]['name'].dropna().unique()
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
        Initialise la section d'historique des calculs dans l'interface utilisateur.

        Configure la liste des calculs précédents, les boutons pour supprimer ou modifier un calcul,
        et les boutons pour exporter ou importer les données de l'historique.
        
        Args:
            main_layout (QVBoxLayout): Le layout principal auquel ajouter la section d'historique.
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

    def initUIGraphButtons(self, main_layout):
        """
        Initialise les boutons pour générer des graphiques dans l'interface utilisateur.

        Configure les boutons pour créer différents types de graphiques (diagramme en secteurs, barres empilées, etc.)
        et les connecte aux méthodes correspondantes pour afficher les graphiques.
        
        Args:
            main_layout (QVBoxLayout): Le layout principal auquel ajouter les boutons de graphiques.
        """
        graph_summary_label = QLabel("Générer des résumés graphiques :")
        main_layout.addWidget(graph_summary_label)
        # Boutons pour les graphiques line 1 (Pie, Bar, Proportional Bar)
        self.generate_pie_button = QPushButton('Diagramme en Secteurs')
        self.generate_pie_button.setToolTip(
            "Affiche un diagramme en secteurs pour les émissions totales."
        )
        self.generate_bar_button = QPushButton('Barres Empilées à 100%')
        self.generate_bar_button.setToolTip(
            "Affiche un graphique en barres empilées à 100% pour les émissions totales."
        )

        self.generate_proportional_bar_button = QPushButton('Barres Empilées (prix)')
        self.generate_proportional_bar_button.setToolTip(
            "Affiche un graphique en barres empilées pour les émissions totales."
        )

        # Layout pour les boutons de graphiques line 1
        buttons_layout_graph_line1 = QHBoxLayout()
        buttons_layout_graph_line1.addWidget(self.generate_pie_button)
        buttons_layout_graph_line1.addWidget(self.generate_bar_button)
        buttons_layout_graph_line1.addWidget(self.generate_proportional_bar_button)
        main_layout.addLayout(buttons_layout_graph_line1)

        # Boutons pour les graphiques line 2 (Stacked Bar, Nacres Bar)
        self.generate_stacked_bar_consumables_button = QPushButton("Barres Empilées (Consommables)")
        self.generate_stacked_bar_consumables_button.setToolTip(
            "Affiche un graphique en barres empilées uniquement pour les consommables à quantité > 0."
        )

        self.generate_nacres_bar_button = QPushButton("Barres NACRES")
        self.generate_nacres_bar_button.setToolTip(
            "Affiche un graphique en barres pour les consommables avec les valeurs NACRES."
        )

        self.generate_proportional_bar_button_mass = QPushButton('Barres Empilées (Masse)')
        self.generate_proportional_bar_button_mass.setToolTip(
            "Affiche un graphique en barres empilées pour les émissions totales avec un calcul se basant sur la masse."
        )
        # Layout pour les boutons de graphiques line 2
        buttons_layout_graph_line2 = QHBoxLayout()
        buttons_layout_graph_line2.addWidget(self.generate_stacked_bar_consumables_button)
        buttons_layout_graph_line2.addWidget(self.generate_nacres_bar_button)
        buttons_layout_graph_line2.addWidget(self.generate_proportional_bar_button_mass)
        main_layout.addLayout(buttons_layout_graph_line2)

        main_layout.addSpacing(5)

    def initUISignals(self):
        """
        Initialise les connexions de signaux et slots dans l'interface utilisateur.

        Connecte les événements des widgets (comme les changements de sélection dans les comboboxes,
        les clics sur les boutons, les changements de texte dans les champs de recherche) aux méthodes correspondantes pour gérer les interactions utilisateur.
        """
        self.header_label.linkActivated.connect(self.toggle_text_display)
        self.category_combo.currentIndexChanged.connect(self.update_subcategories)
        self.subcategory_combo.currentIndexChanged.connect(self.update_subsubcategory_names)
        self.subcategory_combo.currentIndexChanged.connect(self.update_quantity_visibility)

        self.conso_search_field.textChanged.connect(
            lambda text: self.update_conso_filtered_combo(filter_text=text)
        )
        self.search_field.textChanged.connect(self.on_search_text_changed)
        self.subsub_name_combo.currentIndexChanged.connect(self.update_years)
        self.subsub_name_combo.currentIndexChanged.connect(self.on_subsub_name_changed)

        self.year_combo.currentIndexChanged.connect(self.update_unit)
        self.year_combo.currentIndexChanged.connect(self.update_conso_filtered_combo)

        self.calculate_button.clicked.connect(self.calculate_emission)
        self.delete_button.clicked.connect(self.delete_selected_calculation)
        self.modify_button.clicked.connect(self.modify_selected_calculation)
        self.export_button.clicked.connect(self.export_data)
        self.import_button.clicked.connect(self.import_data)

        self.generate_pie_button.clicked.connect(self.generate_pie_chart)
        self.generate_bar_button.clicked.connect(self.generate_bar_chart)
        self.generate_proportional_bar_button.clicked.connect(self.generate_proportional_bar_chart)
        self.generate_stacked_bar_consumables_button.clicked.connect(self.generate_stacked_bar_consumables)
        self.generate_nacres_bar_button.clicked.connect(self.generate_nacres_bar_chart)
        self.generate_proportional_bar_button_mass.clicked.connect(self.generate_proportional_bar_chart_mass)     

        self.history_list.itemDoubleClicked.connect(self.modify_selected_calculation)
        self.add_machine_button.clicked.connect(self.add_machine)
        self.conso_filtered_combo.currentIndexChanged.connect(self.on_conso_filtered_changed)

    # ------------------------------------------------------------------
    # Fonctions pour gérer filtres & masques
    # ------------------------------------------------------------------
    def on_search_text_changed(self, text):
        """
        Gère l'événement de changement de texte dans le champ de recherche.

        Met à jour les noms des sous-sous-catégories et les consommables filtrés en fonction du texte de recherche saisi par l'utilisateur,
        puis synchronise les sélections après la recherche.
        
        Args:
            text (str): Le texte actuellement saisi dans le champ de recherche.
        """
        self.update_subsubcategory_names()
        self.update_conso_filtered_combo(filter_text=None)
        self.synchronize_after_search()

    def synchronize_after_search(self):
        """
        Synchronise les sélections après une opération de recherche.

        Ajuste les index des comboboxes des sous-sous-catégories et des consommables si nécessaire,
        et met à jour la visibilité de la barre "Quantité".
        """
        c_subsub = self.subsub_name_combo.count()
        if c_subsub == 2:
            self.subsub_name_combo.setCurrentIndex(1)

        c_nacres = self.conso_filtered_combo.count()
        if c_nacres == 2:
            self.conso_filtered_combo.setCurrentIndex(1)

        self.update_quantity_visibility()

    def update_subcategories(self):
        """
        Met à jour les sous-catégories en fonction de la catégorie sélectionnée.

        Configure la visibilité des widgets en fonction de la catégorie choisie (par exemple, masque les éléments non pertinents pour les machines),
        met à jour les items des comboboxes, gère les champs spécifiques aux véhicules, et appelle les méthodes pour gérer la visibilité des consommables.
        """
        category = self.category_combo.currentText()

        if category == 'Machine':
            # Masquer tout ce qui n’est pas "machine"
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
            self.machine_group.setVisible(True)
            self.machine_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

            # Masquer le bouton "Gestion des Consommables"
            self.manage_consumables_button.setVisible(False)

            # Masquer les autres éléments liés aux consommables
            self.conso_filtered_label.setVisible(False)
            self.conso_filtered_combo.setVisible(False)
            self.conso_search_label.setVisible(False)
            self.conso_search_field.setVisible(False)
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)

        else:
            # Réafficher la zone "standard"
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
            self.machine_group.setVisible(False)
            self.machine_group.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

            # Contrôler la visibilité du bouton "Gestion des Consommables" uniquement pour 'Achats'
            if category == 'Achats':
                self.manage_consumables_button.setVisible(True)
            else:
                self.manage_consumables_button.setVisible(False)

            # Mettre à jour les sous-catégories
            subcats = self.data[self.data['category'] == category]['subcategory'].dropna().unique()
            self.subcategory_combo.clear()
            self.subcategory_combo.addItems(sorted(subcats.astype(str)))

            # Cas particulier : Véhicules => on affiche le champ "jours"
            if category == "Véhicules":
                self.days_label.setVisible(True)
                self.days_field.setVisible(True)
                self.days_field.setEnabled(True)
            else:
                self.days_label.setVisible(False)
                self.days_field.setVisible(False)
                self.days_field.setEnabled(False)

            # APRES avoir mis à jour subcategory_combo, on appelle update_subsubcategory_names()
            self.update_subsubcategory_names()

            # => On appelle notre fonction pour afficher/masquer la zone NACRES
            self.update_nacres_visibility()

    def update_nacres_visibility(self):
        """
        Met à jour la visibilité de la zone des consommables (NACRES).

        Affiche ou masque les éléments liés aux consommables en fonction de la catégorie sélectionnée et de la sous-catégorie.
        Si la catégorie est 'Achats' et que la sous-catégorie contient 'Consommables', affiche les éléments,
        sinon les masque.
        """
        category = self.category_combo.currentText()
        subcat = self.subcategory_combo.currentText()

        if category == 'Achats' and subcat and 'Consommables' in subcat:
            # On affiche la zone NACRES
            self.conso_filtered_label.setVisible(True)
            self.conso_filtered_combo.setVisible(True)
            self.conso_search_label.setVisible(True)
            self.conso_search_field.setVisible(True)
            # On met à jour la liste des consommables
            self.update_conso_filtered_combo()
        else:
            # On masque la zone NACRES (et quantité)
            self.conso_filtered_label.setVisible(False)
            self.conso_filtered_combo.setVisible(False)
            self.conso_search_label.setVisible(False)
            self.conso_search_field.setVisible(False)
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)

    def update_subsubcategory_names(self):
        """
        Met à jour les noms des sous-sous-catégories en fonction de la catégorie et sous-catégorie sélectionnées.

        Filtre les données en fonction des sélections actuelles, applique le filtre de recherche si nécessaire,
        et met à jour la combobox des noms. Ajoute également "non renseignée" comme option par défaut.
        """
        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        search_text = self.search_field.text().lower()

        mask = (self.data['category'] == category)
        if subcategory:
            mask &= (self.data['subcategory'] == subcategory)

        filtered_data = self.data[mask]

        # Construction "subsubcategory - name"
        subsub_names = (
            filtered_data['subsubcategory'].fillna('')
            + ' - '
            + filtered_data['name'].fillna('')
        ).str.strip(' - ')

        # On rend unique
        subsub_names_unique = subsub_names.unique()

        # Appliquer la recherche
        if search_text:
            subsub_names_filtered = [s for s in subsub_names_unique if search_text in s.lower()]
        else:
            subsub_names_filtered = list(subsub_names_unique)

        subsub_names_filtered.insert(0, "non renseignée")

        self.subsub_name_combo.blockSignals(True)
        self.subsub_name_combo.clear()
        nr = subsub_names_filtered.pop(0)
        subsub_names_filtered = sorted(subsub_names_filtered)
        subsub_names_filtered.insert(0, nr)
        self.subsub_name_combo.addItems(subsub_names_filtered)
        self.subsub_name_combo.blockSignals(False)

        self.update_years()

    def update_years(self):
        """
        Met à jour la combobox des années disponibles en fonction de la sélection actuelle.

        Filtre les données en fonction de la catégorie, sous-catégorie, sous-sous-catégorie et nom sélectionnés,
        récupère les années disponibles et les ajoute à la combobox des années. Met à jour l'unité de mesure en conséquence.
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
        Met à jour l'unité de mesure en fonction des sélections actuelles.

        Filtre les données en fonction des sélections actuelles et récupère l'unité de mesure correspondante.
        Met à jour le label et l'état du champ d'entrée de la valeur. Si aucune donnée n'est trouvée, désactive le champ d'entrée.
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
            (self.data['name'].fillna('') == name)
        )
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
        Met à jour la combobox des consommables filtrés en fonction d'un texte de filtre.

        Remplit la combobox avec les consommables qui correspondent au texte de filtre saisi par l'utilisateur.
        Ajoute également "non renseignée" comme option par défaut. Bloque temporairement les signaux pour éviter des déclenchements intempestifs.
        
        Args:
            filter_text (str, optional): Le texte utilisé pour filtrer les consommables. Par défaut, None.
        """
        self.conso_filtered_combo.blockSignals(True)
        self.conso_filtered_combo.clear()
        self.conso_filtered_combo.addItem("non renseignée")

        if filter_text is None:
            filter_text = ""
        else:
            filter_text = filter_text.lower()

        for idx, row in self.data_masse.iterrows():
            full_code = row.get('Code NACRES', '').strip()
            consommable = row.get('Consommable', '').strip()
            display_text = f"{full_code} - {consommable}"
            if not filter_text or filter_text in display_text.lower():
                self.conso_filtered_combo.addItem(display_text)

        self.conso_filtered_combo.blockSignals(False)
        self.update_quantity_visibility()

    def on_subsub_name_changed(self):
        """
        Gère l'événement de changement de sélection dans la combobox des noms des sous-sous-catégories.

        Filtre les consommables en fonction du nom sélectionné, met à jour la combobox des consommables,
        et affiche la barre "Quantité" si un consommable valide est sélectionné.
        """
        subsub_name = self.subsub_name_combo.currentText()
        if not subsub_name or subsub_name == "non renseignée":
            # Réinitialiser la combo conso
            self.conso_filtered_combo.blockSignals(True)
            self.conso_filtered_combo.clear()
            self.conso_filtered_combo.addItem("non renseignée")
            self.conso_filtered_combo.blockSignals(False)
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)
            return

        # Récupère les 4 premiers caractères comme code NACRES approximatif
        code_nacres_4 = subsub_name[:4]

        filtered_items = []
        for idx, row in self.data_masse.iterrows():
            full_code = row.get('Code NACRES', '').strip()
            consommable = row.get('Consommable', '').strip()
            display_text = f"{full_code} - {consommable}"
            if full_code.startswith(code_nacres_4):
                filtered_items.append(display_text)

        self.conso_filtered_combo.blockSignals(True)
        self.conso_filtered_combo.clear()
        self.conso_filtered_combo.addItem("non renseignée")
        for it in sorted(filtered_items):
            self.conso_filtered_combo.addItem(it)
        self.conso_filtered_combo.blockSignals(False)

        if len(filtered_items) == 1:
            self.conso_filtered_combo.setCurrentIndex(1)
        else:
            self.conso_filtered_combo.setCurrentIndex(0)

        self.update_quantity_visibility()

    def on_conso_filtered_changed(self):
        """
        Gère l'événement de changement de sélection dans la combobox des consommables filtrés.

        Met à jour la catégorie à 'Achats' si nécessaire, sélectionne la sous-catégorie "Consommables",
        et ajuste la sélection des sous-sous-catégories en fonction du consommable sélectionné.
        Affiche la barre "Quantité" si un consommable valide est sélectionné.
        """
        sel_text = self.conso_filtered_combo.currentText()
        if not sel_text or sel_text == "non renseignée":
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)
            # Forcer subsub_name => "non renseignée"
            self.subsub_name_combo.blockSignals(True)
            idx_nr = self.subsub_name_combo.findText("non renseignée")
            if idx_nr != -1:
                self.subsub_name_combo.setCurrentIndex(idx_nr)
            else:
                self.subsub_name_combo.setCurrentIndex(0)
            self.subsub_name_combo.blockSignals(False)
            self.update_unit()
            return

        # Récupérer codeNACRES_4
        code_nacres_4 = sel_text[:4]

        # Forcer la catégorie Achats, sous-cat contenant "Consommables"
        idx_cat = self.category_combo.findText("Achats")
        if idx_cat >= 0:
            self.category_combo.blockSignals(True)
            self.category_combo.setCurrentIndex(idx_cat)
            self.category_combo.blockSignals(False)

        # Chercher sous-cat "Consommables"
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

        # On appelle update_subsubcategory_names() pour lister toutes les subsub
        self.update_subsubcategory_names()

        # Ensuite, on cherche la subsub dont .str[:4] == code_nacres_4
        filtered_data = self.data[
            (self.data['category'] == "Achats") &
            (self.data['subcategory'].str.contains("Consommables", na=False)) &
            (self.data['subsubcategory'].fillna('').str[:4] == code_nacres_4)
        ]
        if filtered_data.empty:
            # subsub => "non renseignée"
            self.subsub_name_combo.blockSignals(True)
            idx_nr = self.subsub_name_combo.findText("non renseignée")
            if idx_nr != -1:
                self.subsub_name_combo.setCurrentIndex(idx_nr)
            else:
                self.subsub_name_combo.setCurrentIndex(0)
            self.subsub_name_combo.blockSignals(False)
        else:
            row = filtered_data.iloc[0]
            real_subsub = row['subsubcategory'] or ''
            real_name = row['name'] or ''
            new_subsub_text = f"{real_subsub} - {real_name}".strip(" - ")

            self.subsub_name_combo.blockSignals(True)
            idx_ss = self.subsub_name_combo.findText(new_subsub_text)
            if idx_ss != -1:
                self.subsub_name_combo.setCurrentIndex(idx_ss)
            else:
                # On ajoute
                self.subsub_name_combo.addItem(new_subsub_text)
                self.subsub_name_combo.setCurrentIndex(self.subsub_name_combo.count() - 1)
            self.subsub_name_combo.blockSignals(False)

        self.quantity_label.setVisible(True)
        self.quantity_input.setVisible(True)

        self.update_unit()

    def update_quantity_visibility(self):
        """
        Met à jour la visibilité de la barre "Quantité" en fonction de la catégorie sélectionnée et du consommable.

        Affiche la barre "Quantité" uniquement si la catégorie est 'Achats' et qu'un consommable valide est sélectionné.
        Pour toutes les autres catégories, la barre "Quantité" reste masquée.
        """
        category = self.category_combo.currentText()

        if category != 'Achats':
            # Pour toutes les catégories sauf 'Achats', masquer la barre "Quantité"
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)
        else:
            # Pour la catégorie 'Achats', déterminer la visibilité basée sur le consommable
            current_nacres = self.conso_filtered_combo.currentText()
            if not current_nacres or current_nacres == "non renseignée":
                self.quantity_label.setVisible(False)
                self.quantity_input.setVisible(False)
            else:
                self.quantity_label.setVisible(True)
                self.quantity_input.setVisible(True)

    def split_subsub_name(self, subsub_name):
        """
        Met à jour la visibilité de la barre "Quantité" en fonction de la catégorie sélectionnée et du consommable.

        Affiche la barre "Quantité" uniquement si la catégorie est 'Achats' et qu'un consommable valide est sélectionné.
        Pour toutes les autres catégories, la barre "Quantité" reste masquée.
        """
        if ' - ' in subsub_name:
            subsub, name = subsub_name.split(' - ', 1)
        else:
            subsub, name = '', subsub_name
        return subsub.strip(), name.strip()
    
    # ------------------------------------------------------------------
    # Calculs d'émissions
    # ------------------------------------------------------------------
    
    def calculate_emission(self):
        """
        Calcule les émissions de carbone pour la catégorie sélectionnée.

        Gère les calculs spécifiques aux catégories, notamment les machines,
        en récupérant les données saisies par l'utilisateur, en appelant le CarbonCalculator,
        et en ajoutant les résultats à l'historique des calculs. Met à jour également le total des émissions.
        """
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

        # Gérer NACRES si Achats
        code_nacres = 'NA'
        consommable = 'NA'
        if category == 'Achats' and subsubcategory:
            code_nacres = subsubcategory[:4]

        # Récup combo NACRES (si Achats)
        selected_nacres = (self.conso_filtered_combo.currentText()
                        if self.conso_filtered_combo.isVisible() else None)
        if selected_nacres and selected_nacres != "non renseignée" and " - " in selected_nacres:
            code_nacres, consommable = selected_nacres.split(" - ", 1)

        # Lecture du champ input_field => c'est un nombre "km/jour" si Véhicules, "€" si Achats, etc.
        try:
            input_text = self.input_field.text().strip().replace(',', '.')
            val = float(input_text)
            if val < 0:
                raise ValueError("Valeur négative interdite.")
        except ValueError:
            QMessageBox.warning(self, 'Erreur', 'Veuillez entrer une valeur numérique positive.')
            return

        # Nombre de jours
        days = int(self.days_field.text()) if (self.days_field.isEnabled() and self.days_field.text()) else 1

        # !! IMPORTANT !!
        # On NE MULTIPLIE PAS PAR `days` ICI si c’est un Véhicule.
        # On envoie 'val' = "km/jour" et 'days' séparément, 
        # afin que carbon_calculator fasse total_value = val * days.
        #
        # Pour Achats (ou autres), c'est pareil : on envoie juste la valeur (ex. euros tot ou /jour).
        # => carbon_calculator décidera s'il multiplie ou non.

        # Calcul massique => quantity
        quantity = 0
        if self.quantity_label.isVisible() and self.quantity_input.isVisible():
            try:
                quantity_str = self.quantity_input.text().strip()
                quantity = int(quantity_str) if quantity_str else 0
            except:
                quantity = 0

        data_dict = {
            'category': category,
            'subcategory': subcategory,
            'subsubcategory': subsubcategory,
            'name': category_nacres,
            'year': year,
            'value': val,   # c’est km/jour pour Véhicules, euros pour Achats, etc.
            'days': days,
            'code_nacres': code_nacres,
            'consommable': consommable,
            'quantity': quantity,
        }

        # Appel unifié
        ep, ep_err, em, em_err, tm, msg = self.carbon_calculator.compute_emission_data(data_dict)
        if msg:
            self.result_area.setText(msg)
            return

        new_data = {
            'category': category,
            'subcategory': subcategory,
            'subsubcategory': subsubcategory,
            'name': category_nacres,
            # On stocke la valeur journalière => 'value'
            'value': val,
            'days': days,
            'emissions_price': ep,
            'emissions_price_error': ep_err,
            'emission_mass': em,
            'emission_mass_error': em_err,
            'total_mass': tm,
            'code_nacres': code_nacres,
            'consommable': consommable,
            'unit': self.current_unit,
            'quantity': quantity,
        }

        self.create_or_update_history_item(new_data)
        self.update_total_emissions()
        self.input_field.clear()
        self.data_changed.emit()

    def modify_selected_calculation(self):
        """
        Modifie un calcul sélectionné dans l'historique.

        Ouvre une boîte de dialogue pour permettre à l'utilisateur de modifier les données d'un calcul existant.
        Si la modification est acceptée, recalcule les émissions et met à jour l'historique ainsi que les totaux.
        """
        selected_item = self.history_list.currentItem()
        if not selected_item:
            QMessageBox.warning(self, 'Erreur', 'Veuillez sélectionner un calcul à modifier.')
            return

        old_data = selected_item.data(Qt.UserRole)
        if not old_data:
            QMessageBox.warning(self, 'Erreur', 'Aucune donnée disponible pour cet élément.')
            return

        dialog = EditCalculationDialog(self, data=old_data, 
                                    main_data=self.data, 
                                    data_masse=self.data_masse, 
                                    data_materials=self.data_materials)
        if dialog.exec() == QDialog.Accepted:
            modified_data = dialog.modified_data
            print("Debug - Nouveau self.modified_data :", modified_data)

            # On suppose que modified_data['value'] = val/jour
            # et modified_data['days'] = days.
            ep, ep_err, em, em_err, tm, msg_price = self.carbon_calculator.compute_emission_data(modified_data)
            if msg_price:
                self.result_area.setText(msg_price)
                return

            # On met à jour les champs
            modified_data['emissions_price'] = ep
            modified_data['emissions_price_error'] = ep_err
            modified_data['emission_mass'] = em
            modified_data['emission_mass_error'] = em_err
            modified_data['total_mass'] = tm

            self.history_list.takeItem(self.history_list.row(selected_item))
            self.create_or_update_history_item(modified_data)
            self.update_total_emissions()
            self.data_changed.emit()

    def update_total_emissions(self):
        """
        Met à jour le total global des émissions en agrégeant les données de l'historique.

        Calcule le total des émissions basées sur les prix et les masses des différents calculs,
        en prenant en compte les incertitudes associées. Affiche les résultats agrégés dans la zone de résultats.
        Recalcule la somme globale des émissions depuis l'historique,
        en distinguant :

        1) le total (prix) pour tous les items,
        2) le total (prix) uniquement pour les items massiques,
        3) le total massique.
        """
        import math

        total_all_price = 0.0
        total_all_price_err_sq = 0.0

        total_mass_price = 0.0
        total_mass_price_err_sq = 0.0

        total_mass = 0.0
        total_mass_err_sq = 0.0

        for i in range(self.history_list.count()):
            item = self.history_list.item(i)
            data = item.data(Qt.UserRole)
            if not data:
                continue

            # ----- Partie PRIX -----
            e_price = float(data.get('emissions_price', 0.0) or 0.0)
            e_price_err = float(data.get('emissions_price_error', 0.0) or 0.0)

            # Somme sur TOUS les items
            total_all_price += e_price
            total_all_price_err_sq += (e_price_err ** 2)

            # ----- Partie MASSE -----
            e_mass = float(data.get('emission_mass', 0.0) or 0.0)
            e_mass_err = float(data.get('emission_mass_error', 0.0) or 0.0)

            if e_mass > 0:
                # Cet item a un calcul massique
                total_mass_price += e_price
                total_mass_price_err_sq += (e_price_err ** 2)

            total_mass += e_mass
            total_mass_err_sq += (e_mass_err ** 2)

        # Conversion des erreurs au sens "racine de la somme en quadrature"
        all_price_err = math.sqrt(total_all_price_err_sq)
        mass_price_err = math.sqrt(total_mass_price_err_sq)
        mass_err = math.sqrt(total_mass_err_sq)

        # Finalement, on met tout dans self.result_area
        # => 3 lignes
        self.result_area.setText(
            f"1) Total des émissions (prix) [tous items] : {total_all_price:.4f} ± {all_price_err:.4f} kg CO₂e\n"
            f"2) Émissions (prix) [items massiques] : {total_mass_price:.4f} ± {mass_price_err:.4f} kg CO₂e\n"
            f"3) Émissions massiques : {total_mass:.4f} ± {mass_err:.4f} kg CO₂e"
        )

    def create_or_update_history_item(self, data, item=None):
        """
        Crée ou met à jour un élément dans l'historique des calculs.

        Formate le texte de l'élément en fonction de la catégorie du calcul et ajoute l'élément à la liste historique.
        Si un élément existe déjà, le met à jour avec les nouvelles données.
        
        Args:
            data (dict): Le dictionnaire contenant les données du calcul à ajouter ou mettre à jour.
            item (QListWidgetItem, optional): L'élément existant à mettre à jour. Par défaut, None.
        
        Returns:
            QListWidgetItem: L'élément ajouté ou mis à jour dans l'historique.
        """
        category = data.get('category', '')
        subcategory = data.get('subcategory', '')
        subsubcategory = data.get('subsubcategory', '')
        name = data.get('name', '')
        value = data.get('value', 0.0)
        unit = data.get('unit', '')
        ep = data.get('emissions_price', 0.0)
        ep_err = data.get('emissions_price_error', 0.0)
        em = data.get('emission_mass', 0.0)
        em_err = data.get('emission_mass_error', 0.0)
        tm = data.get('total_mass', 0.0)
        code_nacres = data.get('code_nacres', 'NA')
        consommable = data.get('consommable', 'NA')

        def fmt_err(val, err):
            if err is not None and err > 0:
                return f"{val:.4f} ± {err:.4f}"
            else:
                return f"{val:.4f}"

        if category == 'Machine':
            item_text = (
                f"Machine - {subcategory} - {value:.2f} kWh : "
                f"{fmt_err(ep, ep_err)} kg CO₂e"
            )
        elif category == 'Véhicules':
            days = data.get('days', 1)
            
            try:
                km_per_day = float(value) #/ days if days else float(total_km)
                total_km = km_per_day * days
            except (ValueError, ZeroDivisionError):
                km_per_day = 0
                total_km = km_per_day * days
            
            item_text = (
                f"{category} - {subcategory} - {code_nacres} - {name} : "
                f"{km_per_day:.2f} km/jour sur {days} jours, total {total_km} {unit} : "
                f"{fmt_err(ep, ep_err)} kg CO₂e"
            )
        else:
            # Achats / Autres
            prix_str = fmt_err(ep, ep_err)
            item_text = (
                f"{category} - {subcategory[:12]} - {code_nacres} - {name} - "
                f"Dépense: {value} {unit} : {prix_str} kg CO₂e"
            )
            if consommable != 'NA':
                item_text += f" [Consommable: {consommable}]"
            if em != 0.0 and tm != 0.0:
                mass_str = fmt_err(em, em_err)
                item_text += f" - Masse {tm:.4f} kg : {mass_str} kg CO₂e"

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

    def delete_selected_calculation(self):
        """
        Supprime le calcul actuellement sélectionné dans l'historique.

        Retire l'élément sélectionné de la liste historique et met à jour le total des émissions.
        """
        sel_row = self.history_list.currentRow()
        if sel_row >= 0:
            self.history_list.takeItem(sel_row)
            self.update_total_emissions()
            self.data_changed.emit()

    def export_data(self):
        """
        Exporte les données de l'historique des calculs vers un fichier.

        Ouvre une boîte de dialogue pour permettre à l'utilisateur de choisir le format de fichier (CSV, Excel, HDF5),
        puis enregistre les données de l'historique dans le fichier sélectionné. Affiche un message de confirmation ou d'erreur.
        """
        from PySide6.QtWidgets import QFileDialog
        import pandas as pd
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer l'historique", "",
            "Fichier CSV (*.csv);;Fichier Excel (*.xlsx);;Fichier HDF5 (*.h5);;Tous les fichiers (*)"
        )
        if not file_name:
            return

        rows = []
        for i in range(self.history_list.count()):
            itm = self.history_list.item(i)
            d = itm.data(Qt.UserRole)
            if d:
                rows.append(d)

        if not rows:
            QMessageBox.information(self, "Export", "Aucun élément dans l'historique.")
            return

        df = pd.DataFrame(rows)
        _, ext = os.path.splitext(file_name)
        ext = ext.lower()

        try:
            if ext == '.csv':
                df.to_csv(file_name, index=False, sep=';')
            elif ext == '.xlsx':
                df.to_excel(file_name, index=False)
            elif ext == '.h5':
                df.to_hdf(file_name, key='history', mode='w')
            else:
                df.to_csv(file_name, index=False, sep=';')
            QMessageBox.information(self, "Export", f"Exporté avec succès dans {file_name}")
        except Exception as e:
            QMessageBox.warning(self, "Erreur Export", f"{e}")

    def import_data(self):
        """
        Importe des données dans l'historique des calculs à partir d'un fichier.

        Ouvre une boîte de dialogue pour permettre à l'utilisateur de sélectionner un fichier (CSV, Excel, HDF5),
        lit les données du fichier, convertit les colonnes attendues, et ajoute les éléments à l'historique.
        Affiche un message de confirmation ou d'erreur.
        """
        from PySide6.QtWidgets import QFileDialog
        import pandas as pd
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Importer l'historique", "",
            "Fichier CSV (*.csv);;Fichier Excel (*.xlsx);;Fichier HDF5 (*.h5);;Tous les fichiers (*)"
        )
        if not file_name:
            return

        _, ext = os.path.splitext(file_name)
        ext = ext.lower()
        try:
            if ext == '.csv':
                df = pd.read_csv(file_name, sep=';')
            elif ext == '.xlsx':
                df = pd.read_excel(file_name)
            elif ext == '.h5':
                df = pd.read_hdf(file_name, key='history')
            else:
                df = pd.read_csv(file_name, sep=';')
        except Exception as e:
            QMessageBox.warning(self, "Erreur Import", f"Impossible de lire le fichier : {e}")
            return

        # Convertir les colonnes attendues
        for col in ["value", "quantity", "days", "emissions_price", "emission_mass", "total_mass"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        for col in ["category", "subcategory", "subsubcategory", "name",
                    "code_nacres", "consommable", "unit"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()

        count_imported = 0
        for idx, row in df.iterrows():
            new_data = row.to_dict()
            self.create_or_update_history_item(new_data)
            count_imported += 1

        QMessageBox.information(self, "Import", f"{count_imported} élément(s) importé(s) depuis {file_name}.")
        self.update_total_emissions()
        self.data_changed.emit()

    def add_machine(self):
        """
        Ajoute une machine au calculateur de bilan carbone.

        Récupère les informations saisies par l'utilisateur (nom, puissance, temps d'utilisation, nombre de jours, type d'électricité),
        calcule les émissions basées sur ces données en utilisant le CarbonCalculator,
        ajoute le résultat à l'historique des calculs, et met à jour le total des émissions.
        Efface également les champs de saisie après l'ajout.
        
        Affiche un message d'erreur si les valeurs saisies ne sont pas valides ou si le facteur d'émission pour le type d'électricité n'est pas trouvé.
        """
        try:
            machine_name = self.machine_name_field.text().strip()
            power = float(self.power_field.text().strip())         # kW
            usage_time = float(self.usage_time_field.text().strip())  # h/jour
            days = int(self.days_machine_field.text().strip())

            if usage_time > 24:
                QMessageBox.warning(self, 'Erreur', "Le temps d'utilisation ne peut pas dépasser 24h/jour.")
                return

            total_usage = power * usage_time * days  # kWh total

            electricity_type = self.electricity_combo.currentText()

            data_dict = {
                'category': 'Machine',
                'subcategory': machine_name,
                'subsubcategory': '',  # Pas de sous-sous-catégorie pour les machines
                'electricity_type': electricity_type,
                'year': '',  # Pas d'année pour les machines
                'value': total_usage,  # kWh
                'days': days,
                'code_nacres': 'NA',  # Pas de NACRES pour les machines
                'consommable': 'NA',  # Pas de consommable pour les machines
                'quantity': 0,         # Pas de quantité pour les machines
            }

            ep, ep_err, em, em_err, tm, msg = self.carbon_calculator.compute_emission_data(data_dict)
            if msg:
                QMessageBox.warning(self, 'Erreur', msg)
                return

            new_data = {
                'category': 'Machine',
                'subcategory': machine_name,
                'subsubcategory': '',
                'electricity_type': electricity_type,
                'value': total_usage,  # kWh
                'unit': 'kWh',
                'emissions_price': ep,
                'emissions_price_error': ep_err,
                'emission_mass': em,
                'emission_mass_error': em_err,
                'total_mass': tm,
                'code_nacres': 'NA',
                'consommable': 'NA',
                'quantity': 0,
            }

            self.create_or_update_history_item(new_data)
            self.update_total_emissions()

            # Clear champs
            self.machine_name_field.clear()
            self.power_field.clear()
            self.usage_time_field.clear()
            self.days_machine_field.clear()
            self.input_field.clear()
            self.data_changed.emit()

        except ValueError:
            QMessageBox.warning(self, 'Erreur', "Veuillez entrer des valeurs numériques valides.")
            return

    # ------------------------------------------------------------------
    # Graphiques
    # ------------------------------------------------------------------
    def generate_chart(self, chart_type):
        """
        Génère et affiche un graphique en fonction du type spécifié.

        Args:
            chart_type (str): Le type de graphique à générer. 
                            Les types valides sont :
                            - 'pie' : Diagramme en secteurs.
                            - 'bar' : Graphique à barres empilées à 100%.
                            - 'proportional_bar' : Graphique à barres empilées proportionnelles.
                            - 'stacked_bar_consumables' : Graphique à barres empilées pour les consommables.
                            - 'nacres_bar' : Graphique basé sur les codes NACRES.
        """
        # Détermine le nom de l'attribut correspondant à la fenêtre graphique.
        # Exemple : pour 'pie', on recherche 'pie_chart_window'.
        window_attr = f"{chart_type}_chart_window"

        # Récupère la fenêtre existante pour ce type de graphique (si elle existe déjà).
        window = getattr(self, window_attr, None)

        if window is None:  # Si la fenêtre n'existe pas encore :
            # Dictionnaire associant chaque type de graphique à sa classe correspondante.
            window_class = {
                'pie': PieChartWindow,
                'bar': BarChartWindow,
                'proportional_bar': ProportionalBarChartWindow,
                'stacked_bar_consumables': StackedBarConsumablesWindow,
                'nacres_bar': NacresBarChartWindow,
                'proportional_bar_mass': ProportionalBarChartNacresWindow
            }.get(chart_type)

            # Vérifie si le type demandé est valide (i.e., présent dans le dictionnaire).
            if window_class is None:
                # Affiche un avertissement si le type de graphique est inconnu.
                QMessageBox.warning(self, "Erreur", f"Type de graphique inconnu : {chart_type}")
                return  # Sort de la fonction sans rien faire.

            # Crée une nouvelle instance de la fenêtre pour le type de graphique spécifié.
            window = window_class(self)

            # Connecte le signal `finished` de la fenêtre pour réinitialiser l'attribut
            # correspondant lorsque la fenêtre est fermée.
            # Cela permet de recréer une nouvelle fenêtre la prochaine fois que cette fonction est appelée.
            window.finished.connect(lambda: setattr(self, window_attr, None))

            # Stocke la fenêtre créée dans l'attribut correspondant à son type.
            setattr(self, window_attr, window)
        else:
            # Si la fenêtre existe déjà, met à jour ses données.
            window.refresh_data()

        # Affiche la fenêtre graphique.
        window.show()
        window.raise_()  # Amène la fenêtre au premier plan.
        window.activateWindow()  # Active la fenêtre pour qu'elle soit prête à recevoir des interactions.

    def generate_pie_chart(self):
        self.generate_chart('pie')

    def generate_bar_chart(self):
        self.generate_chart('bar')

    def generate_proportional_bar_chart(self):
        self.generate_chart('proportional_bar')

    def generate_stacked_bar_consumables(self):
        self.generate_chart('stacked_bar_consumables')

    def generate_nacres_bar_chart(self):
        self.generate_chart('nacres_bar')

    def generate_proportional_bar_chart_mass(self):
        self.generate_chart('proportional_bar_mass')

    def show_sources_popup(self, link_str):
        """
        Affiche une fenêtre contextuelle contenant les sources et références de l'application.

        Ouvre une boîte de dialogue modale avec une liste détaillée de sources, références et articles scientifiques,
        incluant des liens interactifs pour accéder aux ressources externes.
        
        Args:
            link_str (str): La chaîne de lien activée (non utilisée dans cette fonction).
        """
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