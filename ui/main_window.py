# SPDX-License-Identifier: GPL-3.0-or-later
# windows/main_window.py, LABeCO2 ©
# Copyright (c), 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
# Auteur : Alexandre Souchaud — labeco2.contact@gmail.com
#
# Ce programme est distribué sous licence :
#   - GNU GPL v3 (ou toute version ultérieure), pour une utilisation libre et non commerciale ;
#
# Vous pouvez consulter la GPL ici : https://www.gnu.org/licenses/gpl-3.0.fr.html
#
# Date de création : 01/10/2024 — Version V2.1 du 10/04/2025
# DOI: 10.5281/zenodo.15243498


import sys
import os
import math
import re
import json
import sqlite3
import pandas as pd
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QComboBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QVBoxLayout, QHBoxLayout, QWidget, QFrame,
    QFormLayout, QDialog, QScrollArea, QSizePolicy, QAbstractItemView, QToolTip,
    QToolButton, QStyle, QListView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QCursor, QIntValidator, QDoubleValidator
from shiboken6 import isValid

from ui.data_manager import DataManager
from ui.carbon_calculator import CarbonCalculator
from ui.nacres_metadata import load_nacres_options
from ui.display_utils import (
    clean_text,
    display_unit,
    format_quantity,
    format_subcategory_label,
    is_consumables_subcategory,
    looks_like_liquid_commercial_product,
    normalize_nacres_prefix,
    normalize_search,
    safe_float,
)

from utils.data_loader import (
    get_user_data_path,
    init_user_data,
    load_logo,
    resolve_sqlite_path,
)
from utils.color_utils import CATEGORY_COLORS
from scenarios.manip_type_db import ManipsTypeDB
from ui.charts.pie_chart import PieChartWindow
from ui.charts.bar_chart_price_mass import BarChartWindow
from ui.charts.bar_chart_proportional import ProportionalBarChartWindow
from ui.data_mass_window import DataMassWindow
from ui.edit_calculation_dialog import EditCalculationDialog
from ui.charts.bar_chart_consumables import StackedBarConsumablesWindow
from ui.charts.nacres_bar_chart import NacresBarChartWindow
from ui.charts.pareto_chart import ParetoChartWindow
from ui.charts.transport_chart import TransportChartWindow
from ui.charts.transport_consumable_chart import TransportConsumableChartWindow
from ui.charts.transport_factor_chart import TransportFactorChartWindow
from ui.charts.transport_scenario_chart import TransportScenarioChartWindow
from ui.charts.transport_top_chart import TransportTopChartWindow
from ui.charts.nacres_proportional import ProportionalBarChartNacresWindow
from ui.charts.coverage_overview import CoverageWindow
from ui.charts.coverage_by_category import CoverageCategoryWindow
from ui.user_manip_dialog import UserManipDialog
from ui.charts.history_utils import iter_history_data


_NACRES_NEW_NO_FE_COLOR = QColor(255, 210, 150)
_NACRES_NEW_NO_FE_TOOLTIP = (
    "Nouveau code NACRES 2026 : le projet GES 1point5 n'a pas encore défini "
    "de facteur d'émission pour cette catégorie."
)
_DETAIL_COMBO_WIDTH = 330
_MAIN_SEARCH_WIDTH = 220
_MAIN_COMBO_VISIBLE_ITEMS = 15


class CompactPopupComboBox(QComboBox):
    """QComboBox dont le popup reste exactement à la largeur de la case.

    Sur macOS le popup natif peut paraître flottant. On force ici la fenêtre du
    popup à la même largeur que la combo et on la repositionne juste sous le
    widget pour qu'elle se déroule pile à son emplacement.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        view = QListView(self)
        view.setUniformItemSizes(True)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setTextElideMode(Qt.TextElideMode.ElideRight)
        view.setStyleSheet("QListView { background: white; color: black; }")
        self.setView(view)

    def showPopup(self) -> None:
        width = self.width()
        view = self.view()
        view.setMinimumWidth(width)
        view.setMaximumWidth(width)
        super().showPopup()
        popup = view.window()
        popup.setMinimumWidth(width)
        popup.setMaximumWidth(width)
        height = min(popup.height(), 420)
        anchor = self.mapToGlobal(self.rect().bottomLeft())
        popup.setGeometry(anchor.x(), anchor.y(), width, height)


def _configure_detail_combo(combo: QComboBox) -> None:
    combo.setFixedWidth(_DETAIL_COMBO_WIDTH)
    combo.setMaxVisibleItems(_MAIN_COMBO_VISIBLE_ITEMS)
    combo.view().setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)


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
        init_user_data()  # initialise les données utilisateur au premier lancement compilé
        # base_path  : données en lecture seule (bundlées dans l'exécutable)
        # user_path  : données modifiables par l'utilisateur (persistantes entre sessions)
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
            user_path = get_user_data_path()
        else:
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            user_path = base_path

        # Chemin de la base de données SQLite pour les manips type
        db_path = os.path.join(user_path, "scenarios", "manips_type.sqlite")
        self.manips_db = ManipsTypeDB(db_path=db_path)

        try:
            sqlite_path = resolve_sqlite_path(base_path, user_path)
            self.data_manager = DataManager(
                base_path,
                user_path=user_path,
                sqlite_path=sqlite_path,
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger les données : {e}")
            sys.exit(1)

        # 2) Récup DataFrame
        self.data = self.data_manager.get_main_data()
        self.data_masse = self.data_manager.get_data_masse()
        self.data_materials = self.data_manager.get_data_materials()
        self.data_liquides = self.data_manager.get_data_liquides() 

        # 3) CarbonCalculator
        self.carbon_calculator = CarbonCalculator(self.data_manager)

        # Variables
        self.current_unit = None

        # Fenêtres graphiques
        self.pie_chart_window = None
        self.bar_chart_window = None
        self.proportional_bar_chart_window = None
        self.data_mass_window = None
        self.stacked_bar_consumables_window = None
        self.nacres_bar_chart_window = None
        self.pareto_chart_window = None
        self.transport_chart_window = None
        self.transport_consumable_chart_window = None
        self.transport_factor_chart_window = None
        self.transport_scenario_chart_window = None
        self.transport_top_chart_window = None
        self.coverage_chart_window = None
        self.coverage_category_chart_window = None

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
        self.reset_search_button = None
        self.toggle_graph_buttons_button = None
        self.graph_buttons_container = None
        self.summary_pdf_button = None

        # NACRES
        self.conso_filtered_label = None
        self.conso_filtered_combo = None
        self.quantity_label = None
        self.quantity_input = None
        self.prix_unitaire_label = None
        self.prix_info_button = None
        self._current_prix_unitaire_info_text = ""
        self._current_prix_unitaire = None   # float ou None
        self._current_masse_unitaire_g = None  # float > 0 si vrac solide, None sinon
        self.fe_massique_label = None
        self.fe_massique_input = None
        self.category_color_dot = None
        self.indicator_nacres = None
        self.indicator_conso = None
        self.origine_label = None
        self.origine_combo = None
        self.origine_info_button = None
        self.origine_row_widget = None
        self._nacres_options = []
        self._nacres_by_code = {}
        self._consumable_search_entries = []
        self._consumable_prefixes_all = set()
        self._purchase_rows_by_prefix = {}
        self._purchase_row_cache = {}
        self._load_nacres_options()
        self._rebuild_search_indexes()

        self.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #a9a9a9;
                border-radius: 4px;
                padding: 2px 8px;
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
        self.result_area = QLabel()
        self.result_area.setWordWrap(True)
        self.result_area.setTextFormat(Qt.RichText)
        self.result_area.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._result_show_ok(
            "<b>Toutes catégories (méthode prix) :</b> 0.0000 "
            "<span style='color:#6b9e7a; font-size:11px'>± 0.0000</span> kg CO₂e<br>"
            "<b>Consommables (méthode prix) :</b> 0.0000 "
            "<span style='color:#6b9e7a; font-size:11px'>± 0.0000</span> kg CO₂e<br>"
            "<b>Consommables (méthode masse) :</b> 0.0000 "
            "<span style='color:#6b9e7a; font-size:11px'>± 0.0000</span> kg CO₂e"
        )
        main_layout.addWidget(self.result_area)

        # Label des sources et méthodologie
        self.sources_label = QLabel(
            "L'ensemble des sources sont à retrouver <a href=\"sources\">ici</a>. "
            "La méthodologie est présentée <a href=\"methodo\">ici</a>."
        )
        self.sources_label.setTextFormat(Qt.RichText)
        self.sources_label.setOpenExternalLinks(False)
        self.sources_label.setTextInteractionFlags(Qt.TextBrowserInteraction | Qt.LinksAccessibleByMouse)
        self.sources_label.setAlignment(Qt.AlignCenter)
        self.sources_label.linkActivated.connect(self._on_footer_link)
        main_layout.addWidget(self.sources_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        container = QWidget()
        container.setLayout(main_layout)
        scroll_area.setWidget(container)
        self.setCentralWidget(scroll_area)

        self.initUISignals()
        self.update_subcategories()

        self.resize(780, 700)
        screen = QApplication.primaryScreen()
        screen_size = screen.size()
        self.setMaximumSize(screen_size.width(), screen_size.height())
        self.setMinimumSize(780, 700)

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
            représentent un levier d'action significatif pour atteindre cet objectif.
        </p>
        <p>
            Cette application vise à <span style="font-weight:bold; color:#1fa543;">calculer le bilan carbone</span> 
            (<span style="font-weight:bold; color:#2196F3;">eCO₂</span>) des activités de laboratoire pour 
            <span style="font-weight:bold; color:#1fa543;">sensibiliser</span> à leur empreinte écologique 
            et identifier les postes les plus énergivores afin d'
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
            tout en maintenant l'excellence et l'innovation au cœur de ses priorités.
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

        self.add_calcul_button = QPushButton("▼ Ajouter un calcul")
        self.add_manip_button = QPushButton("▼ Ajouter une manip type")
        self.add_calcul_button.setCheckable(True)
        self.add_manip_button.setCheckable(True)
        self.add_calcul_button.setFixedHeight(40)
        self.add_manip_button.setFixedHeight(40)
        collapsible_button_style = """
            QPushButton {
                background-color: #f5faf7;
                color: #14532d;
                border: 1px solid #cfe8d8;
                border-radius: 5px;
                padding: 7px 10px;
                font-weight: 600;
                text-align: left;
            }
            QPushButton:hover { background-color: #edf7f1; }
            QPushButton:checked {
                background-color: #e8f2fb;
                border-color: #b6d4ec;
                color: #17415f;
            }
        """
        self.add_calcul_button.setStyleSheet(collapsible_button_style)
        self.add_manip_button.setStyleSheet(collapsible_button_style)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_calcul_button)
        button_layout.addWidget(self.add_manip_button)

        main_layout.addLayout(button_layout)

    def add_logo(self):
        """
        Ajoute le logo de l'application à l'en-tête.

        Charge l'image du logo, la redimensionne de manière proportionnelle,
        et l'affiche dans un QLabel aligné au centre. En cas d'échec du chargement, affiche un message d'erreur.
        """
        pixmap = load_logo()
        self.logo_label = QLabel()
        if pixmap.isNull():
            QMessageBox.warning(self, 'Erreur', "Impossible de charger le logo de l'application.")
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

    def toggle_graph_buttons_section(self, checked):
        """
        Affiche ou masque la section des boutons de graphiques.
        """
        if self.graph_buttons_container is None:
            return

        self.graph_buttons_container.setVisible(checked)
        if self.toggle_graph_buttons_button is not None:
            if checked:
                self.toggle_graph_buttons_button.setText("▲ Masquer les options graphiques")
            else:
                self.toggle_graph_buttons_button.setText("▼ Afficher les options graphiques")

    def _set_manip_type_controls_visible(self, visible):
        self.manip_type_label.setVisible(visible)
        self.manip_type_combo.setVisible(visible)
        self.add_manip_type_button.setVisible(visible)
        self.update_delete_manip_button()

    def _set_button_checked_safely(self, button, checked):
        button.blockSignals(True)
        button.setChecked(checked)
        button.blockSignals(False)

    def _update_add_section_button_texts(self):
        if self.add_calcul_button is not None:
            if self.add_calcul_button.isChecked():
                self.add_calcul_button.setText("▲ Masquer l'ajout d'un calcul")
            else:
                self.add_calcul_button.setText("▼ Ajouter un calcul")
        if self.add_manip_button is not None:
            if self.add_manip_button.isChecked():
                self.add_manip_button.setText("▲ Masquer les manips type")
            else:
                self.add_manip_button.setText("▼ Ajouter une manip type")

    def toggle_calcul_section(self, checked):
        if checked:
            self._set_button_checked_safely(self.add_manip_button, False)
            self._set_manip_type_controls_visible(False)
            self.show_calcul_section()
        else:
            self.existing_group.setVisible(False)
            self.machine_group.setVisible(False)
        self._update_add_section_button_texts()

    def toggle_manip_type_section(self, checked):
        if checked:
            self._set_button_checked_safely(self.add_calcul_button, False)
            self.existing_group.setVisible(False)
            self.machine_group.setVisible(False)
            self.show_manip_type_section()
        else:
            self._set_manip_type_controls_visible(False)
        self._update_add_section_button_texts()

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
        self.subcategory_combo.setMaxVisibleItems(_MAIN_COMBO_VISIBLE_ITEMS)

        # Nom (subsub_name) + barre de recherche
        self.subsub_name_label = QLabel('Nom:')
        self.subsub_name_combo = CompactPopupComboBox()
        _configure_detail_combo(self.subsub_name_combo)
        self.search_label = QLabel('Recherche:')
        self.search_field = QLineEdit()
        self.search_field.setFixedWidth(_MAIN_SEARCH_WIDTH)
        self.reset_search_button = QToolButton()
        self.reset_search_button.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        self.reset_search_button.setToolTip("Réinitialiser les recherches")
        self.reset_search_button.setAutoRaise(True)
        self.reset_search_button.setFixedSize(28, 28)

        self.indicator_nacres = QLabel("✗")
        self.indicator_nacres.setFixedWidth(20)
        self.indicator_nacres.setStyleSheet("color: #dc2626; font-size: 15px; font-weight: bold;")

        nom_layout = QHBoxLayout()
        nom_layout.addWidget(self.indicator_nacres)
        nom_layout.addWidget(self.subsub_name_combo)
        nom_layout.addWidget(self.search_label)
        nom_layout.addWidget(self.search_field)
        nom_layout.addWidget(self.reset_search_button)

        # NACRES / consommable
        self.conso_filtered_label = QLabel("Consommables:")
        self.conso_filtered_label.setToolTip(
            "Matières premières, produits chimiques/biologiques et organismes vivants"
        )
        self.conso_filtered_combo = CompactPopupComboBox()
        _configure_detail_combo(self.conso_filtered_combo)
        self.conso_search_label = QLabel("Recherche:")
        self.conso_search_field = QLineEdit()
        self.conso_search_field.setFixedWidth(_MAIN_SEARCH_WIDTH)

        self.indicator_conso = QLabel("✗")
        self.indicator_conso.setFixedWidth(20)
        self.indicator_conso.setStyleSheet("color: #dc2626; font-size: 15px; font-weight: bold;")

        conso_layout = QHBoxLayout()
        conso_layout.addWidget(self.indicator_conso)
        conso_layout.addWidget(self.conso_filtered_combo)
        conso_layout.addWidget(self.conso_search_label)
        conso_layout.addWidget(self.conso_search_field)

        self.year_combo = QComboBox(parent=self)
        self.year_combo.setVisible(False)

        self.quantity_label = QLabel("Quantité:")
        self.quantity_input = QLineEdit()
        self.quantity_label.setVisible(False)
        self.quantity_input.setVisible(False)

        self.fe_massique_label = QLabel("Facteur d'émission :")
        self.fe_massique_input = QLineEdit()
        self.fe_massique_input.setPlaceholderText("ex: 12.5 (optionnel)")
        self.fe_massique_label.setVisible(False)
        self.fe_massique_input.setVisible(False)

        self.origine_label = QLabel("Provenance:")
        self.origine_combo = QComboBox()
        origins = self.data_manager.get_transport_origins()
        self.origine_combo.addItems(origins)
        self.origine_combo.setFixedWidth(200)
        self.origine_info_button = QPushButton("Plus d'info")

        origine_row = QHBoxLayout()
        origine_row.setContentsMargins(0, 0, 0, 0)
        origine_row.setSpacing(6)
        origine_row.addWidget(self.origine_combo)
        origine_row.addWidget(self.origine_info_button)
        origine_row.addStretch()
        self.origine_row_widget = QWidget()
        self.origine_row_widget.setLayout(origine_row)

        self.origine_label.setVisible(False)
        self.origine_row_widget.setVisible(False)

        self.prix_unitaire_label = QLabel("Prix unitaire : —")
        self.prix_unitaire_label.setVisible(False)
        self.prix_info_button = QPushButton("Plus d'info")
        self.prix_info_button.setVisible(False)

        prix_unitaire_layout = QHBoxLayout()
        prix_unitaire_layout.setContentsMargins(0, 0, 0, 0)
        prix_unitaire_layout.setSpacing(6)
        prix_unitaire_layout.addWidget(self.prix_unitaire_label)
        prix_unitaire_layout.addWidget(self.prix_info_button)
        prix_unitaire_layout.addStretch()

        self.masse_manquante_label = QLabel("")
        self.masse_manquante_label.setStyleSheet("")
        self.masse_manquante_label.setWordWrap(True)
        self.masse_manquante_label.setVisible(False)

        self.contenant_warning_label = QLabel("")
        self.contenant_warning_label.setWordWrap(True)
        self.contenant_warning_label.setVisible(False)

        self.manage_consumables_button = QPushButton("Enrichir le consommable choisi")
        self.manage_consumables_button.setToolTip("Enrichir le consommable choisi")
        self.manage_consumables_button.setEnabled(False)
        self.manage_consumables_button.setMaximumWidth(230)
        self.add_consumable_button = QPushButton("Ajouter un consommable")
        self.add_consumable_button.setMaximumWidth(190)
        self.add_emission_factor_button = QPushButton("Ajouter un facteur d'émission")
        self.add_emission_factor_button.setMaximumWidth(230)
        # self.manage_consumables_button.setStyleSheet("""
        #     QPushButton {
        #         text-decoration: underline;
        #         color: blue;
        #         background: none;
        #         border: none;
        #         padding: 0;
        #     }
        #     QPushButton:hover {
        #         color: darkblue;
        #     }
        # """)

        self.input_label = QLabel('Entrez la valeur journalière :')
        self.input_field = QLineEdit()
        self.input_field.setEnabled(False)

        self.days_label = QLabel("Nombre de jours d'utilisation:")
        self.days_field = QLineEdit()
        self.days_field.setEnabled(False)
        self.days_label.setVisible(False)
        self.days_field.setVisible(False)

        self.calculate_button = QPushButton('Calculer le Bilan Carbone')
        self.calculate_button.setStyleSheet("""
            QPushButton {
                background-color: #1a7f4b;
                color: #ffffff;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #15693f; }
            QPushButton:pressed { background-color: #0f5231; }
            QPushButton:disabled { background-color: #a8d5bc; color: #ffffff; }
        """)

        # Indicateur coloré de catégorie (pastille)
        self.category_color_dot = QFrame()
        self.category_color_dot.setFixedSize(12, 12)
        self.category_color_dot.setStyleSheet("background-color: #888888; border-radius: 6px;")
        category_row = QHBoxLayout()
        category_row.setContentsMargins(0, 0, 0, 0)
        category_row.setSpacing(6)
        category_row.addWidget(self.category_color_dot)
        category_row.addWidget(self.category_combo)
        category_row_widget = QWidget()
        category_row_widget.setLayout(category_row)

        form_layout = QFormLayout()
        form_layout.setSpacing(5)
        form_layout.setLabelAlignment(Qt.AlignRight)

        form_layout.addRow(self.category_label, category_row_widget)
        form_layout.addRow(self.subcategory_label, self.subcategory_combo)
        form_layout.addRow(self.subsub_name_label, nom_layout)
        form_layout.addRow(self.conso_filtered_label, conso_layout)
        consumable_actions_layout = QHBoxLayout()
        consumable_actions_layout.setContentsMargins(0, 0, 0, 0)
        consumable_actions_layout.setSpacing(6)
        consumable_actions_layout.addWidget(self.manage_consumables_button)
        consumable_actions_layout.addWidget(self.add_consumable_button)
        consumable_actions_layout.addWidget(self.add_emission_factor_button)
        consumable_actions_layout.addStretch()
        self.consumable_actions_widget = QWidget()
        self.consumable_actions_widget.setLayout(consumable_actions_layout)
        form_layout.addRow("", self.consumable_actions_widget)

        existing_layout = QVBoxLayout()
        # Ajoute ici le form_layout, les champs et le bouton "Calculer" déjà configurés
        existing_layout.setSpacing(5)
        existing_layout.addLayout(form_layout)
        existing_layout.addWidget(self.quantity_label)
        existing_layout.addWidget(self.quantity_input)
        existing_layout.addWidget(self.fe_massique_label)
        existing_layout.addWidget(self.fe_massique_input)
        existing_layout.addWidget(self.origine_label)
        existing_layout.addWidget(self.origine_row_widget)
        existing_layout.addLayout(prix_unitaire_layout)
        existing_layout.addWidget(self.masse_manquante_label)
        existing_layout.addWidget(self.contenant_warning_label)
        existing_layout.addWidget(self.input_label)
        existing_layout.addWidget(self.input_field)
        existing_layout.addWidget(self.days_label)
        existing_layout.addWidget(self.days_field)
        existing_layout.addWidget(self.calculate_button)

        existing_group = QWidget()
        existing_group.setLayout(existing_layout)

        main_layout.addWidget(existing_group)
        
        
        # Liste déroulante pour les manips type (initialement cachée)
        self.manip_type_label = QLabel("Choisissez une manip type :")
        self.manip_type_combo = QComboBox()
        self.manip_type_combo.addItem("Sélectionnez une manip...")
        # On récupère toutes les manips existantes en base (natives + utilisateur·rice)
        manip_names = self.manips_db.list_manips()
        for mn in manip_names:
            self.manip_type_combo.addItem(mn)
        self.add_manip_type_button = QPushButton("Ajouter la manip sélectionnée")
        self.delete_manip_type_button = QPushButton("Supprimer de la base de données la manip sélectionnée")

        # Par défaut, on masque les 3 widgets
        self.manip_type_combo.setVisible(False)
        self.manip_type_label.setVisible(False)
        self.add_manip_type_button.setVisible(False)
        self.delete_manip_type_button.setVisible(False)
        # On les ajoute au layout principal
        main_layout.addWidget(self.manip_type_label)
        main_layout.addWidget(self.manip_type_combo)
        main_layout.addWidget(self.add_manip_type_button)
        main_layout.addWidget(self.delete_manip_type_button)
        
        self.refresh_manip_type_combo()

        existing_group.setVisible(False)
        self.existing_group = existing_group  # Pour pouvoir la montrer plus tard

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
        power_validator = QDoubleValidator(0.001, 99999.0, 3, self)
        power_validator.setNotation(QDoubleValidator.StandardNotation)
        self.power_field.setValidator(power_validator)

        self.usage_time_label = QLabel("Temps d'utilisation par jour (heures):")
        self.usage_time_field = QLineEdit()
        self.usage_time_field.setMaximumWidth(200)
        self.usage_time_field.setValidator(QIntValidator(1, 24, self))

        self.days_machine_label = QLabel("Nombre de jours d'utilisation:")
        self.days_machine_field = QLineEdit()
        self.days_machine_field.setMaximumWidth(200)
        self.days_machine_field.setValidator(QIntValidator(1, 9999, self))

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

        self.history_list = QTableWidget()
        self.history_list.setColumnCount(5)
        self.history_list.setHorizontalHeaderLabels([
            "Catégorie", "Élément", "Valeur", "eCO₂ prix (kg)", "eCO₂ masse (kg)"
        ])
        self.history_list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.history_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_list.verticalHeader().setVisible(False)
        self.history_list.verticalHeader().setDefaultSectionSize(24)
        self.history_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.history_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.history_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.history_list.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.history_list.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.history_list.setFixedHeight(155)
        self.history_list.setStyleSheet(
            "QTableWidget { color: black; }"
            "QHeaderView::section { color: black; font-weight: bold;"
            " background-color: #f3f4f6; padding: 3px; }"
        )
        main_layout.addWidget(self.history_list)

        self.delete_button = QPushButton('Supprimer le(s) calcul(s) sélectionné(s)')
        self.delete_button.setEnabled(False)
        self.modify_button = QPushButton('Modifier le calcul sélectionné')
        self.modify_button.setEnabled(False)

        calc_buttons_layout = QHBoxLayout()
        calc_buttons_layout.setSpacing(1)
        calc_buttons_layout.addWidget(self.delete_button)
        calc_buttons_layout.addWidget(self.modify_button)

        self.export_button = QPushButton('Exporter le bilan calculé')
        self.import_button = QPushButton('Importer un bilan')

        export_import_layout = QHBoxLayout()
        export_import_layout.setSpacing(0)
        export_import_layout.addWidget(self.export_button)
        export_import_layout.addWidget(self.import_button)

        buttons_group_layout = QVBoxLayout()
        buttons_group_layout.setSpacing(0)
        buttons_group_layout.addLayout(calc_buttons_layout)
        buttons_group_layout.addLayout(export_import_layout)

        self.create_user_manip_button = QPushButton("Définir une manip type d'utilisateur")
        buttons_group_layout.addWidget(self.create_user_manip_button)

        main_layout.addLayout(buttons_group_layout)
        main_layout.addSpacing(5)

    def initUIGraphButtons(self, main_layout):
        self.toggle_graph_buttons_button = QPushButton("▼ Afficher les options graphiques")
        self.toggle_graph_buttons_button.setCheckable(True)
        self.toggle_graph_buttons_button.setChecked(False)
        self.toggle_graph_buttons_button.setToolTip("Afficher ou masquer les boutons de graphiques.")
        self.toggle_graph_buttons_button.setStyleSheet("""
            QPushButton {
                background-color: #eef7f2;
                color: #14532d;
                border: 1px solid #bbdfc8;
                border-radius: 5px;
                padding: 6px 10px;
                font-weight: 600;
                text-align: left;
            }
            QPushButton:hover { background-color: #e2f1e8; }
            QPushButton:checked {
                background-color: #e8f2fb;
                border-color: #b6d4ec;
                color: #17415f;
            }
        """)
        main_layout.addWidget(self.toggle_graph_buttons_button)

        self.graph_buttons_container = QWidget()
        self.graph_buttons_container.setObjectName("graphButtonsContainer")
        graph_buttons_layout = QVBoxLayout()
        graph_buttons_layout.setContentsMargins(12, 10, 12, 10)
        graph_buttons_layout.setSpacing(6)
        self.graph_buttons_container.setLayout(graph_buttons_layout)
        self.graph_buttons_container.setStyleSheet(
            "#graphButtonsContainer { background-color: #f4f9f6; border: 1px solid #d5eadc; "
            "border-radius: 6px; }"
            "#graphButtonsContainer QLabel { border: none; background: transparent; }"
            "QPushButton { background-color: #ffffff; }"
        )

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)

        graph_summary_label = QLabel("<b>Génération de résumés graphiques :</b>")
        graph_summary_label.setStyleSheet("border: none; background: transparent;")
        header_row.addWidget(graph_summary_label)

        header_row.addStretch()

        self.summary_pdf_button = QPushButton("📄 Résumé PDF total")
        self.summary_pdf_button.setToolTip(
            "Génère un PDF complet : résumé des émissions, tableau de l'historique et tous les graphiques."
        )
        self.summary_pdf_button.setStyleSheet(
            "QPushButton { background-color: #1d4ed8; color: white; border: none;"
            " border-radius: 4px; padding: 4px 12px; font-weight: 600; }"
            "QPushButton:hover { background-color: #1e40af; }"
            "QPushButton:pressed { background-color: #1e3a8a; }"
            "QPushButton:disabled { background-color: #93c5fd; color: #e0e7ff; }"
        )
        header_row.addWidget(self.summary_pdf_button)

        graph_buttons_layout.addLayout(header_row)

        _HEADER_FIRST = (
            "font-weight: 700; font-size: 13px; color: #374151;"
            " padding-top: 4px; margin-top: 2px;"
        )
        _HEADER = (
            "border-top: 1px solid #cbd5e1;"
            " font-weight: 700; font-size: 13px; color: #374151;"
            " padding-top: 8px; margin-top: 8px;"
        )

        def _section_header(text, first=False):
            lbl = QLabel(text)
            lbl.setStyleSheet(_HEADER_FIRST if first else _HEADER)
            return lbl

        # ── Section 1 : Émissions globales ──────────────────────────────
        graph_buttons_layout.addWidget(_section_header("Émissions globales", first=True))

        self.generate_pie_button = QPushButton("Camembert")
        self.generate_pie_button.setToolTip(
            "Diagramme en secteurs : répartition des émissions totales par catégorie."
        )
        self.generate_bar_button = QPushButton("Barres par catégorie")
        self.generate_bar_button.setToolTip(
            "Barres empilées à 100% : distribution relative des émissions par catégorie."
        )
        self.generate_proportional_bar_button = QPushButton("Répartition monétaire")
        self.generate_proportional_bar_button.setToolTip(
            "Barres proportionnelles : émissions par catégorie, pondérées par les dépenses monétaires."
        )
        self.generate_pareto_button = QPushButton("Pareto")
        self.generate_pareto_button.setToolTip(
            "Diagramme de Pareto : postes classés par émissions décroissantes"
            " avec courbe cumulée — identifie les 20 % de postes responsables de 80 % des émissions."
        )

        row1 = QHBoxLayout()
        row1.setSpacing(4)
        row1.addWidget(self.generate_pie_button)
        row1.addWidget(self.generate_bar_button)
        row1.addWidget(self.generate_proportional_bar_button)
        row1.addWidget(self.generate_pareto_button)
        graph_buttons_layout.addLayout(row1)

        # ── Section 2 : Consommables ─────────────────────────────────────
        graph_buttons_layout.addWidget(_section_header("Consommables"))

        self.generate_stacked_bar_consumables_button = QPushButton("Prix vs Masse")
        self.generate_stacked_bar_consumables_button.setToolTip(
            "Barres empilées : comparaison des émissions carbone calculées"
            " par le coût monétaire et par la masse."
        )
        self.generate_nacres_bar_button = QPushButton("Par code NACRES (coût)")
        self.generate_nacres_bar_button.setToolTip(
            "Empreinte carbone des consommables calculée à partir de leur valeur monétaire,"
            " groupée par code NACRES."
        )
        self.generate_proportional_bar_button_mass = QPushButton("Par code NACRES (masse)")
        self.generate_proportional_bar_button_mass.setToolTip(
            "Empreinte carbone des consommables calculée à partir de leur masse,"
            " groupée par code NACRES."
        )

        row2 = QHBoxLayout()
        row2.setSpacing(4)
        row2.addWidget(self.generate_stacked_bar_consumables_button)
        row2.addWidget(self.generate_nacres_bar_button)
        row2.addWidget(self.generate_proportional_bar_button_mass)
        row2.addStretch()
        graph_buttons_layout.addLayout(row2)

        # ── Section 3 : Transport des consommables ──────────────────────
        graph_buttons_layout.addWidget(_section_header("Transport des consommables"))

        self.generate_transport_consumable_button = QPushButton("Par consommable")
        self.generate_transport_consumable_button.setToolTip(
            "Barres empilées par consommable : part matière et part transport,"
            " avec une couleur de transport par provenance."
        )
        self.generate_transport_top_button = QPushButton("Top transport")
        self.generate_transport_top_button.setToolTip(
            "Classement des consommables qui pèsent le plus dans les émissions de transport."
        )
        self.generate_transport_button = QPushButton("Par provenance (matière + transport)")
        self.generate_transport_button.setToolTip(
            "Barres empilées par provenance : décomposition des émissions masse"
            " en part matière et part transport."
        )
        self.generate_transport_factor_button = QPushButton("Par provenance (transport seul)")
        self.generate_transport_factor_button.setToolTip(
            "Barres par provenance : émissions kg CO₂e dues uniquement au transport,"
            " avec le facteur (kg CO₂e/kg) et le pourcentage du total masse affiché."
        )
        self.generate_transport_scenario_button = QPushButton("Scénario Europe")
        self.generate_transport_scenario_button.setToolTip(
            "Compare les émissions transport actuelles à un scénario où les provenances hors France/Europe"
            " sont remplacées par une provenance Europe."
        )

        row3_transport = QHBoxLayout()
        row3_transport.setSpacing(4)
        row3_transport.addWidget(self.generate_transport_consumable_button)
        row3_transport.addWidget(self.generate_transport_top_button)
        row3_transport.addWidget(self.generate_transport_button)
        graph_buttons_layout.addLayout(row3_transport)

        row3_transport_b = QHBoxLayout()
        row3_transport_b.setSpacing(4)
        row3_transport_b.addWidget(self.generate_transport_factor_button)
        row3_transport_b.addStretch()
        row3_transport_b.addWidget(self.generate_transport_scenario_button)
        graph_buttons_layout.addLayout(row3_transport_b)

        # ── Section 4 : Couverture ───────────────────────────────────────
        graph_buttons_layout.addWidget(_section_header("Couverture méthodologique"))

        self.generate_coverage_button = QPushButton("Couverture globale")
        self.generate_coverage_button.setToolTip(
            "Répartition globale de la couverture : quantitatif physique,"
            " proxy monétaire, non couvert."
        )
        self.generate_coverage_category_button = QPushButton("Couverture par catégorie")
        self.generate_coverage_category_button.setToolTip(
            "Répartition par catégorie de la méthode de calcul utilisée."
        )

        row3 = QHBoxLayout()
        row3.setSpacing(4)
        row3.addWidget(self.generate_coverage_button)
        row3.addWidget(self.generate_coverage_category_button)
        row3.addStretch()
        graph_buttons_layout.addLayout(row3)

        graph_buttons_layout.addSpacing(5)
        self.graph_buttons_container.setVisible(False)
        main_layout.addWidget(self.graph_buttons_container)

    def initUISignals(self):
        """
        Initialise les connexions de signaux et slots dans l'interface utilisateur.

        Connecte les événements des widgets (comme les changements de sélection dans les comboboxes,
        les clics sur les boutons, les changements de texte dans les champs de recherche) aux méthodes correspondantes pour gérer les interactions utilisateur.
        """
        self.header_label.linkActivated.connect(self.toggle_text_display)
        self.toggle_graph_buttons_button.toggled.connect(self.toggle_graph_buttons_section)
        self.add_calcul_button.toggled.connect(self.toggle_calcul_section)

        self.category_combo.currentIndexChanged.connect(self.update_subcategories)
        self.subcategory_combo.currentIndexChanged.connect(self.update_subsubcategory_names)
        self.subcategory_combo.currentIndexChanged.connect(self.update_quantity_visibility)
        self.subcategory_combo.currentIndexChanged.connect(self.update_nacres_visibility)

        self.conso_search_field.textChanged.connect(
            lambda text: self.update_conso_filtered_combo(filter_text=text)
        )
        self.conso_search_field.textChanged.connect(self.update_subsubcategory_names)
        self.search_field.textChanged.connect(self.on_search_text_changed)
        self.reset_search_button.clicked.connect(self.reset_search_fields)
        self.subsub_name_combo.currentIndexChanged.connect(self.update_years)
        self.subsub_name_combo.currentIndexChanged.connect(self.on_subsub_name_changed)

        self.year_combo.currentIndexChanged.connect(self.update_unit)
        self.year_combo.currentIndexChanged.connect(self.update_conso_filtered_combo)

        self.calculate_button.clicked.connect(self.calculate_emission)
        self.delete_button.clicked.connect(self.delete_selected_calculation)
        self.modify_button.clicked.connect(self.modify_selected_calculation)
        self.export_button.clicked.connect(self.export_data)
        self.import_button.clicked.connect(self.import_data)
        self.create_user_manip_button.clicked.connect(self.define_user_manip_from_history)
        self.add_manip_button.toggled.connect(self.toggle_manip_type_section)

        self.generate_pie_button.clicked.connect(self.generate_pie_chart)
        self.generate_bar_button.clicked.connect(self.generate_bar_chart)
        self.generate_proportional_bar_button.clicked.connect(self.generate_proportional_bar_chart)
        self.generate_stacked_bar_consumables_button.clicked.connect(self.generate_stacked_bar_consumables)
        self.generate_nacres_bar_button.clicked.connect(self.generate_nacres_bar_chart)
        self.generate_proportional_bar_button_mass.clicked.connect(self.generate_proportional_bar_chart_mass)     
        self.generate_pareto_button.clicked.connect(self.generate_pareto_chart)
        self.generate_transport_consumable_button.clicked.connect(self.generate_transport_consumable_chart)
        self.generate_transport_top_button.clicked.connect(self.generate_transport_top_chart)
        self.generate_transport_button.clicked.connect(self.generate_transport_chart)
        self.generate_transport_factor_button.clicked.connect(self.generate_transport_factor_chart)
        self.generate_transport_scenario_button.clicked.connect(self.generate_transport_scenario_chart)
        self.generate_coverage_button.clicked.connect(self.generate_coverage_chart)
        self.generate_coverage_category_button.clicked.connect(self.generate_coverage_category_chart)
        self.summary_pdf_button.clicked.connect(self.generate_pdf_summary)

        self.history_list.cellDoubleClicked.connect(lambda r, c: self.modify_selected_calculation())
        self.add_machine_button.clicked.connect(self.add_machine)
        self.conso_filtered_combo.currentIndexChanged.connect(self.on_conso_filtered_changed)
        self.quantity_input.textChanged.connect(self._auto_fill_prix)
        self.prix_info_button.clicked.connect(self.show_prix_unitaire_info)
        self.origine_info_button.clicked.connect(self.show_origine_info)
        self.origine_combo.currentIndexChanged.connect(self._update_origine_info_button)

        self.manage_consumables_button.clicked.connect(self.open_data_mass_window)
        self.add_consumable_button.clicked.connect(self.open_data_mass_window_new)
        self.add_emission_factor_button.clicked.connect(self.open_emission_factor_window)

        self.subsub_name_combo.currentIndexChanged.connect(self._update_field_indicators)
        self.conso_filtered_combo.currentIndexChanged.connect(self._update_field_indicators)
        self.input_field.textChanged.connect(self._update_field_indicators)
        self.quantity_input.textChanged.connect(self._update_field_indicators)

        self.add_manip_type_button.clicked.connect(self.add_manip_type_to_history)
        self.delete_manip_type_button.clicked.connect(self.delete_selected_user_manip)
        self.manip_type_combo.currentIndexChanged.connect(self.update_delete_manip_button)

        self.history_list.model().rowsInserted.connect(self._update_graph_buttons_state)
        self.history_list.model().rowsRemoved.connect(self._update_graph_buttons_state)
        self.history_list.model().rowsInserted.connect(self._update_history_buttons_state)
        self.history_list.model().rowsRemoved.connect(self._update_history_buttons_state)
        self.history_list.selectionModel().selectionChanged.connect(self._update_history_buttons_state)
        self._update_graph_buttons_state()
        self._update_history_buttons_state()

    # ------------------------------------------------------------------
    # Helpers d'affichage et de sélection
    # ------------------------------------------------------------------
    def _load_nacres_options(self):
        self._nacres_options = []
        self._nacres_by_code = {}
        sqlite_path = getattr(self.data_manager, "sqlite_path", None)
        if not sqlite_path:
            return
        try:
            with sqlite3.connect(sqlite_path) as conn:
                self._nacres_options = load_nacres_options(conn)
            self._nacres_by_code = {option.code: option for option in self._nacres_options}
        except Exception:
            self._nacres_options = []
            self._nacres_by_code = {}

    def _rebuild_search_indexes(self):
        """Prépare les index utilisés par la recherche consommables/NACRES."""
        self._consumable_search_entries = []
        self._consumable_prefixes_all = set()
        self._purchase_rows_by_prefix = {}
        self._purchase_row_cache = {}

        df = getattr(self, "data_masse", None)
        if (
            df is not None and
            not df.empty and
            self.data_manager.CODE_NACRES_COL in df.columns and
            self.data_manager.CONSOMMABLE_COL in df.columns
        ):
            unit_col = getattr(self.data_manager, "UNITE_LIQUIDE_COL", "Unité liquide")
            for row in df.to_dict("records"):
                full_code = clean_text(row.get(self.data_manager.CODE_NACRES_COL, ""))
                consommable = clean_text(row.get(self.data_manager.CONSOMMABLE_COL, ""))
                prefix = normalize_nacres_prefix(full_code)
                if not consommable or not prefix:
                    continue
                packaging = self._consumable_packaging_label(row)
                source = "liquid" if clean_text(row.get(unit_col)) else "solid"
                search_text = normalize_search(f"{full_code} {consommable} {packaging}")
                self._consumable_search_entries.append(
                    (consommable.casefold(), full_code, consommable, source, search_text, prefix, packaging)
                )
                self._consumable_prefixes_all.add(prefix)

        data = getattr(self, "data", None)
        if data is None or data.empty:
            return
        achats = data[data["category"] == "Achats"].copy()
        if achats.empty:
            return
        subsub = achats["subsubcategory"].fillna("").astype(str).str.strip().str.upper()
        achats = achats.assign(_nacres_prefix=subsub.str[:4])
        for row in achats.to_dict("records"):
            prefix = normalize_nacres_prefix(row.get("_nacres_prefix", ""))
            if not prefix:
                continue
            self._purchase_rows_by_prefix.setdefault(prefix, []).append(row)

    def _ensure_search_indexes(self):
        if not hasattr(self, "_consumable_search_entries") or not hasattr(self, "_purchase_rows_by_prefix"):
            self._rebuild_search_indexes()

    def _populate_subcategory_combo(self, subcategories):
        self.subcategory_combo.clear()
        for subcategory in sorted(clean_text(s) for s in subcategories if clean_text(s)):
            display, tooltip = format_subcategory_label(subcategory)
            self.subcategory_combo.addItem(display, userData=subcategory)
            index = self.subcategory_combo.count() - 1
            if tooltip:
                self.subcategory_combo.setItemData(index, tooltip, Qt.ToolTipRole)

    def _current_subcategory(self):
        data = self.subcategory_combo.currentData()
        return clean_text(data) or clean_text(self.subcategory_combo.currentText())

    def _select_subcategory(self, subcategory):
        subcategory = clean_text(subcategory)
        if not subcategory:
            return False
        index = self.subcategory_combo.findData(subcategory)
        if index < 0:
            display, _ = format_subcategory_label(subcategory)
            index = self.subcategory_combo.findText(display)
        if index >= 0:
            self.subcategory_combo.setCurrentIndex(index)
            return True
        return False

    def _consumable_packaging_label(self, row) -> str:
        conditionnement = clean_text(row.get("condt_ijm", ""))
        if conditionnement:
            return conditionnement

        volume = safe_float(
            row.get(getattr(self.data_manager, "VOLUME_FLACON_COL", "Volume flacon (mL)")),
            default=0.0,
        )
        unit = clean_text(row.get(getattr(self.data_manager, "UNITE_LIQUIDE_COL", "Unité liquide")))
        if volume > 0 and unit:
            return f"{format_quantity(volume)} {unit}"

        nb = safe_float(
            row.get(getattr(self.data_manager, "NOMBRE_PAR_COND_COL", "Nbr par conditionnement")),
            default=0.0,
        )
        if nb > 0:
            return f"{format_quantity(nb)} unité(s)"

        return ""

    def _consumable_display_name(self, consommable: str, packaging: str) -> str:
        name = clean_text(consommable)
        pack = clean_text(packaging)
        if not name:
            return pack
        if not pack:
            return name
        if normalize_search(pack) in normalize_search(name):
            return name
        return f"{name} - {pack}"

    def _add_consumable_combo_item(self, code_nacres, consommable, source="solid", packaging=""):
        code = clean_text(code_nacres)
        name = clean_text(consommable)
        if not code and not name:
            return
        pack = clean_text(packaging)
        display = self._consumable_display_name(name or code, pack)
        metadata = {
            "code_nacres": code,
            "consommable": name,
            "source": source,
            "conditionnement": pack,
        }
        self.conso_filtered_combo.addItem(display, userData=metadata)
        index = self.conso_filtered_combo.count() - 1
        tooltip = []
        if code:
            tooltip.append(f"Code NACRES : {code}")
        if pack:
            tooltip.append(f"Conditionnement : {pack}")
        if source == "liquid":
            tooltip.append("Consommable liquide")
        if tooltip:
            self.conso_filtered_combo.setItemData(index, "\n".join(tooltip), Qt.ToolTipRole)

    def _add_direct_nacres_combo_item(self, code_nacres):
        code = normalize_nacres_prefix(code_nacres)
        if not code:
            return
        self.conso_filtered_combo.addItem(
            "Dépense directe sur ce code NACRES",
            userData={"direct_nacres": True, "code_nacres": code},
        )
        index = self.conso_filtered_combo.count() - 1
        self.conso_filtered_combo.setItemData(
            index,
            "Aucun consommable détaillé n'est requis : le calcul utilisera directement le facteur monétaire du code NACRES sélectionné.",
            Qt.ToolTipRole,
        )

    def _selected_nacres_prefix(self):
        subsub_name = self.subsub_name_combo.currentText() if self.subsub_name_combo else ""
        if not subsub_name or subsub_name == "non renseignée":
            return ""
        subsubcategory, _ = self.split_subsub_name(subsub_name)
        return normalize_nacres_prefix(subsubcategory or subsub_name)

    def _consumable_code_prefixes(self, filter_text: str | None = None) -> set:
        """Codes NACRES pour lesquels la base consommables contient au moins un produit.

        Si filter_text est fourni, seuls les codes dont au moins un consommable
        correspond au filtre sont inclus.
        """
        self._ensure_search_indexes()
        norm_filter = normalize_search(filter_text) if filter_text else None
        if not norm_filter:
            return set(self._consumable_prefixes_all)
        return {
            prefix
            for _, _, _, _, search_text, prefix, _ in self._consumable_search_entries
            if norm_filter in search_text
        }

    def _nacres_prefix_has_consumables(self, code_nacres):
        return normalize_nacres_prefix(code_nacres) in self._consumable_code_prefixes()

    def _purchase_factor_rows_for_nacres(self, code_nacres):
        """Retourne les lignes Achats du référentiel monétaire pour un préfixe NACRES."""
        self._ensure_search_indexes()
        prefix = normalize_nacres_prefix(code_nacres)
        if not prefix:
            return []
        return self._purchase_rows_by_prefix.get(prefix, [])

    def _purchase_factor_row_for_nacres(self, code_nacres, preferred_subcategory=None):
        """Choisit la ligne d'achat à utiliser pour un code NACRES donné."""
        prefix = normalize_nacres_prefix(code_nacres)
        preferred = clean_text(preferred_subcategory)
        cache_key = (prefix, preferred)
        self._ensure_search_indexes()
        if cache_key in self._purchase_row_cache:
            return self._purchase_row_cache[cache_key]

        rows = self._purchase_factor_rows_for_nacres(code_nacres)
        if not rows:
            self._purchase_row_cache[cache_key] = None
            return None

        if preferred:
            for row in rows:
                if clean_text(row.get("subcategory", "")) == preferred:
                    self._purchase_row_cache[cache_key] = row
                    return row

        for row in rows:
            if is_consumables_subcategory(clean_text(row.get("subcategory", ""))):
                self._purchase_row_cache[cache_key] = row
                return row

        self._purchase_row_cache[cache_key] = rows[0]
        return rows[0]

    def _current_subsub_data(self):
        if self.subsub_name_combo is None:
            return {}
        data = self.subsub_name_combo.currentData()
        return data if isinstance(data, dict) else {}

    def _sync_subcategory_from_subsub_selection(self):
        data = self._current_subsub_data()
        target_subcategory = clean_text(data.get("subcategory"))
        if not target_subcategory or target_subcategory == self._current_subcategory():
            return False

        self.subcategory_combo.blockSignals(True)
        changed = self._select_subcategory(target_subcategory)
        self.subcategory_combo.blockSignals(False)

        if changed:
            if self.category_combo.currentText() == "Achats":
                self.subsub_name_label.setText("Code NACRES :")
            else:
                self.subsub_name_label.setText("Nom :")
        return changed

    def _selected_consumable_data(self):
        if self.conso_filtered_combo is None:
            return None
        data = self.conso_filtered_combo.currentData()
        if isinstance(data, dict):
            if data.get("direct_nacres"):
                return None
            name = clean_text(data.get("consommable"))
            code = clean_text(data.get("code_nacres"))
            if name or code:
                return {
                    "code_nacres": code,
                    "consommable": name,
                    "source": clean_text(data.get("source")) or "solid",
                    "conditionnement": clean_text(data.get("conditionnement")),
                }

        text = clean_text(self.conso_filtered_combo.currentText())
        if not text or text == "non renseignée":
            return None
        if " - " in text:
            code, name = text.split(" - ", 1)
            if re.match(r"^[A-Za-z]{2}[0-9]{2}\b", clean_text(code)):
                return {"code_nacres": clean_text(code), "consommable": clean_text(name), "source": "solid", "conditionnement": ""}
        return {"code_nacres": "", "consommable": text, "source": "solid", "conditionnement": ""}

    def _select_consumable_item(self, code_nacres, consommable, packaging=""):
        code_prefix = normalize_nacres_prefix(code_nacres)
        name = clean_text(consommable)
        pack = clean_text(packaging)
        for index in range(self.conso_filtered_combo.count()):
            data = self.conso_filtered_combo.itemData(index)
            if not isinstance(data, dict):
                continue
            item_name = clean_text(data.get("consommable"))
            item_code = clean_text(data.get("code_nacres"))
            item_pack = clean_text(data.get("conditionnement"))
            if (
                item_name == name and
                normalize_nacres_prefix(item_code) == code_prefix and
                (not pack or item_pack == pack)
            ):
                self.conso_filtered_combo.setCurrentIndex(index)
                return True
        return False

    def _nacres_code_mask(self, series, code_nacres):
        if hasattr(self.data_manager, "nacres_code_mask"):
            return self.data_manager.nacres_code_mask(series, code_nacres)
        code_clean = clean_text(code_nacres).upper()
        prefix = normalize_nacres_prefix(code_clean)
        clean_series = series.fillna("").astype(str).str.strip().str.upper()
        return (clean_series == code_clean) | (clean_series.str[:4] == prefix)

    def _infer_code_nacres_for_consumable(self, consommable):
        name = clean_text(consommable)
        if not name:
            return ""
        df = self.data_masse
        if df is not None and not df.empty:
            mask = df[self.data_manager.CONSOMMABLE_COL].astype(str).str.strip() == name
            if mask.any():
                return clean_text(df.loc[mask, self.data_manager.CODE_NACRES_COL].iloc[0])
        if self.data_liquides is not None and not self.data_liquides.empty:
            mask = self.data_liquides.get("Produit", pd.Series(dtype=str)).astype(str).str.strip() == name
            if mask.any():
                return clean_text(self.data_liquides.loc[mask, self.data_manager.CODE_NACRES_COL].iloc[0])
        return ""

    def _set_consumable_controls_visible(self, visible, clear_selection=False):
        """
        Affiche ou masque toute la zone spécifique aux consommables.

        On garde ce nettoyage centralisé pour éviter de laisser visibles le prix
        unitaire ou les avertissements de masse après un changement de catégorie.
        """
        for widget in (
            self.conso_filtered_label,
            self.conso_filtered_combo,
            self.conso_search_label,
            self.conso_search_field,
            self.quantity_label,
            self.quantity_input,
            self.fe_massique_label,
            self.fe_massique_input,
            self.origine_label,
            self.origine_row_widget,
            self.prix_unitaire_label,
            self.prix_info_button,
            self.masse_manquante_label,
            self.contenant_warning_label,
            self.consumable_actions_widget,
            self.manage_consumables_button,
            self.add_consumable_button,
            self.add_emission_factor_button,
        ):
            if widget is not None:
                widget.setVisible(visible)

        if visible:
            self.update_manage_consumable_button_state()
            return

        if self.conso_filtered_combo is not None and clear_selection:
            self.conso_filtered_combo.blockSignals(True)
            self.conso_filtered_combo.clear()
            self.conso_filtered_combo.addItem("non renseignée")
            self.conso_filtered_combo.blockSignals(False)

        if self.conso_search_field is not None and clear_selection:
            self.conso_search_field.blockSignals(True)
            self.conso_search_field.clear()
            self.conso_search_field.blockSignals(False)
        if self.quantity_input is not None and clear_selection:
            self.quantity_input.blockSignals(True)
            self.quantity_input.clear()
            self.quantity_input.blockSignals(False)
        if self.fe_massique_input is not None and clear_selection:
            self.fe_massique_input.blockSignals(True)
            self.fe_massique_input.clear()
            self.fe_massique_input.blockSignals(False)

        self._current_prix_unitaire = None
        self._current_prix_unitaire_info_text = ""
        if self.prix_unitaire_label is not None:
            self.prix_unitaire_label.setToolTip("")
        if self.masse_manquante_label is not None:
            self.masse_manquante_label.setText("")
        if self.contenant_warning_label is not None:
            self.contenant_warning_label.setText("")
        if self.manage_consumables_button is not None:
            self.manage_consumables_button.setEnabled(False)
    # ------------------------------------------------------------------
    # Fonctions pour gérer filtres & masques
    # ------------------------------------------------------------------
    def show_manip_type_section(self):
        """ Affiche la liste déroulante des manips type et masque la section de calcul. """
        # Ne pas retirer le widget du layout, simplement le masquer
        self.existing_group.setVisible(False)
        self.machine_group.setVisible(False)
        self._set_manip_type_controls_visible(True)

    def show_calcul_section(self):
        """
        Affiche la section d'ajout de calcul (pour Achats, Véhicules, etc.) et masque les contrôles des manip types.
        Si la catégorie sélectionnée est "Machine", on garde le sélecteur de catégorie visible
        et on affiche la section Machine.
        """
        current_category = self.category_combo.currentText()
        # Masquer les contrôles des manip types
        self._set_manip_type_controls_visible(False)

        self.existing_group.setVisible(True)
        self.machine_group.setVisible(current_category == "Machine")
        self.category_combo.setEnabled(True)
        self.subcategory_combo.setEnabled(True)
        self.existing_group.adjustSize()
        self._update_field_indicators()

    def calculate_emission_for_item(self, item_data: dict) -> dict:
        """
        Calcule les émissions de carbone pour un seul "item" de la même manière
        que la fonction 'calculate_emission', mais en se basant uniquement sur
        un dictionnaire item_data (sans accès direct à l'UI).

        - Gère le cas 'Machine' comme dans calculate_emission.
        - Reconstruit subsub_name si nécessaire pour en extraire le code NACRES.
        - Appelle compute_emission_data(item_data) pour obtenir ep, ep_err, em, em_err, tm, msg.
        - Stocke ensuite ces résultats dans item_data et le renvoie.

        Args:
            item_data (dict): Contient a minima :
                - category (str)
                - subcategory (str)
                - subsubcategory (str)
                - name (str)           # Pour le code NACRES si Achats
                - value (float)        # km/jour, €...
                - days (int)
                - quantity (int/float)
                - consommable (str)    # S'il s'agit d'un consommable Achats
                - year (str)           # Optionnel
                ...
        Returns:
            dict: item_data mis à jour avec :
                - "emissions_price", "emissions_price_error"
                - "emission_mass", "emission_mass_error"
                - "total_mass"
                - éventuellement "calc_error_msg" si erreur
        """
        # 1) Lire les champs principaux
        category = item_data.get('category', '')
        # # On recompose un subsub_name comme "subsubcategory - name"
        # # pour simuler ce que fait `calculate_emission()` avec `split_subsub_name`
        base_subsub = item_data.get('subsubcategory', '')
        base_name = item_data.get('name', '')
        subsub_name = (base_subsub + " " + base_name).strip(' - ')

        # year = item_data.get('year', '')
        # days = int(item_data.get('days', 1))
        # quantity = item_data.get('quantity', 0)

        # 2) Gérer le cas spécial : Machine
        #    Dans la fonction 'calculate_emission', on appelait self.add_machine().
        #    Ici, on peut soit reproduire la logique de add_machine, soit renvoyer item_data avec un message.
        if category == 'Machine':
            # Ici, par exemple, on "simule" ce que fait add_machine :
            # => on suppose que carbon_calculator gère 'value' = kWh
            ep, ep_err, em, em_err, tm, msg = self.carbon_calculator.compute_emission_data(item_data)
            if msg:
                item_data["calc_error_msg"] = msg
                return item_data
            item_data["emissions_price"] = ep
            item_data["emissions_price_error"] = ep_err
            item_data["emission_mass"] = em
            item_data["emission_mass_error"] = em_err
            item_data["total_mass"] = tm
            return item_data

        # 3) Gérer NACRES si Achats sans écraser un code déjà associé au consommable
        if category == 'Achats':
            code_nacres = clean_text(item_data.get('code_nacres'))
            if not code_nacres or code_nacres == 'NA':
                code_nacres = self._infer_code_nacres_for_consumable(
                    item_data.get("consommable", "")
                )
            if not code_nacres and base_subsub:
                code_nacres = subsub_name[:4]
            item_data['code_nacres'] = code_nacres or 'NA'

        # Si la fonction 'calculate_emission' fait plus de choses, on peut les reproduire ici.

        # 4) Appeler compute_emission_data
        #    => on s'appuie sur la structure existante, 
        #    => item_data doit déjà contenir tout (category, subcategory, subsub, value, days, quantity, etc.)
        ep, ep_err, em, em_err, tm, msg = self.carbon_calculator.compute_emission_data(item_data)

        # 5) Si erreur renvoyée
        if msg:
            item_data["calc_error_msg"] = msg
            return item_data

        # 6) Stocker le résultat dans item_data
        item_data["emissions_price"] = ep
        item_data["emissions_price_error"] = ep_err
        item_data["emission_mass"] = em
        item_data["emission_mass_error"] = em_err
        item_data["total_mass"] = tm

        # 7) Retour
        return item_data

    def add_manip_type_to_history(self):
        """
        Ajoute tous les éléments (items) de la manipulation sélectionnée dans la liste déroulante
        à l'historique en recalculant les émissions pour chacun d'eux.

        1. Vérifie qu'une manip type est sélectionnée dans la combo.
        2. Récupère le nom de la manip (stocké en userData).
        3. Récupère tous les items associés à cette manip depuis la base SQLite.
        4. Pour chaque item, construit un dictionnaire 'new_data' incluant tous les champs essentiels,
        notamment "consommable" et "quantity".
        5. Appelle calculate_emission_for_item(new_data) pour recalculer les émissions.
        6. Si le calcul retourne une erreur (champ "calc_error_msg"), affiche un avertissement et arrête.
        7. Sinon, ajoute l'item recalculé à l'historique et met à jour le total des émissions.
        """
        # 1) Vérifier l'index sélectionné dans la combo
        current_idx = self.manip_type_combo.currentIndex()
        if current_idx <= 0:
            return  # Aucune manip réelle n'est sélectionnée

        # 2) Récupérer le nom de la manip depuis la combo (stocké dans userData)
        manip_data = self.manip_type_combo.itemData(current_idx)
        if isinstance(manip_data, dict):
            manip_name = manip_data.get("name")
        else:
            manip_name = manip_data
        if not manip_name:
            return

        # 3) Récupérer tous les items associés à cette manip depuis la base
        items = self.manips_db.get_manip_items(manip_name)
        if not items:
            QMessageBox.warning(self, "Erreur", f"Aucun item trouvé pour la manip '{manip_name}'.")
            return

        # 4) Pour chaque item, construire le dictionnaire new_data et inclure "consommable" et "quantity"
        for item in items:
            new_data = {
                "category": item["category"],
                "subcategory": item["subcategory"],
                "subsubcategory": item["subsubcategory"],
                "name": item["name"],
                "value": item["value"],
                "unit": item["unit"],
                "quantity": item.get("quantity", 0.0),
                "days": item.get("days", 0),
                "year": item.get("year", 0),
                "electricity_type": item.get("electricity_type", ""),
                "consommable": item.get("consommable", ""),
                "code_nacres": item.get("code_nacres", ""),
                "conditionnement": item.get("conditionnement", ""),
                "origine": item.get("origine", self.data_manager.TRANSPORT_DEFAULT),
            }

            # 5) Recalculer les émissions pour cet item
            updated_data = self.calculate_emission_for_item(new_data)

            # 6) Si un message d'erreur a été renvoyé, afficher une alerte et interrompre
            if "calc_error_msg" in updated_data:
                QMessageBox.warning(self, "Erreur de calcul", updated_data["calc_error_msg"])
                return  # On peut choisir de continuer plutôt que d'arrêter, selon la logique souhaitée

            # 7) Ajouter l'item recalculé à l'historique
            self.create_or_update_history_item(updated_data)

        # Mettre à jour le total des émissions
        self.update_total_emissions()

    def get_selected_manip_info(self):
        current_idx = self.manip_type_combo.currentIndex()
        if current_idx <= 0:
            return None, None

        manip_data = self.manip_type_combo.itemData(current_idx)
        if isinstance(manip_data, dict):
            return manip_data.get("name"), manip_data.get("source")
        if isinstance(manip_data, str):
            return manip_data, self.manips_db.get_manip_source(manip_data)
        return None, None

    def update_delete_manip_button(self):
        if not self.manip_type_combo.isVisible():
            self.delete_manip_type_button.setVisible(False)
            return

        manip_name, manip_source = self.get_selected_manip_info()
        should_show = bool(manip_name and manip_source == ManipsTypeDB.SOURCE_USER)
        self.delete_manip_type_button.setVisible(should_show)

    def delete_selected_user_manip(self):
        manip_name, manip_source = self.get_selected_manip_info()
        if not manip_name:
            return
        if manip_source != ManipsTypeDB.SOURCE_USER:
            QMessageBox.warning(
                self,
                "Suppression impossible",
                "Seules les manips utilisateur·rice peuvent être supprimées."
            )
            self.update_delete_manip_button()
            return

        reply = QMessageBox.question(
            self,
            "Supprimer la manip",
            f"Supprimer définitivement la manip «{manip_name}» de la base de données?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        deleted_count = self.manips_db.delete_manip(manip_name)
        if deleted_count <= 0:
            QMessageBox.warning(
                self,
                "Erreur",
                f"Aucune manip supprimée pour «{manip_name}»."
            )
            return

        QMessageBox.information(
            self,
            "Manip supprimée",
            f"La manip «{manip_name}» a été supprimée."
        )
        self.refresh_manip_type_combo()

    def on_search_text_changed(self, _text):
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

    def reset_search_fields(self):
        """
        Vide les recherches NACRES/consommables et remet les sélections associées à l'état vide.
        """
        for field in (self.search_field, self.conso_search_field):
            if field is not None:
                field.blockSignals(True)
                field.clear()
                field.blockSignals(False)

        self.update_subsubcategory_names()

        self.conso_filtered_combo.blockSignals(True)
        self.conso_filtered_combo.clear()
        self.conso_filtered_combo.addItem("non renseignée")
        self.conso_filtered_combo.blockSignals(False)

        for widget in (
            self.quantity_label,
            self.quantity_input,
            self.fe_massique_label,
            self.fe_massique_input,
            self.origine_label,
            self.origine_row_widget,
            self.prix_unitaire_label,
            self.prix_info_button,
            self.masse_manquante_label,
            self.contenant_warning_label,
        ):
            if widget is not None:
                widget.setVisible(False)

        self._current_prix_unitaire = None
        self._current_prix_unitaire_info_text = ""
        self.prix_unitaire_label.setToolTip("")
        self.masse_manquante_label.setText("")
        self.contenant_warning_label.setText("")
        self.update_manage_consumable_button_state()
        self._update_field_indicators()

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
        Met à jour les sous-catégories et les zones d'interface en fonction de la catégorie sélectionnée.
        Pour "Machine", on masque tous les contrôles standards et on affiche la section Machine.
        Pour les autres catégories, on affiche les contrôles standards et on masque la section Machine.
        """
        category = self.category_combo.currentText()
        calc_section_open = (
            self.add_calcul_button is not None
            and self.add_calcul_button.isChecked()
        )

        if category == 'Machine':
            # Masquer les éléments standards
            self.subcategory_label.setVisible(False)
            self.subcategory_combo.setVisible(False)
            self.search_label.setVisible(False)
            self.search_field.setVisible(False)
            self.reset_search_button.setVisible(False)
            self.subsub_name_label.setVisible(False)
            self.subsub_name_combo.setVisible(False)
            self.year_combo.setVisible(False)
            self.input_label.setVisible(False)
            self.input_field.setVisible(False)
            self.days_label.setVisible(False)
            self.days_field.setVisible(False)
            self.calculate_button.setVisible(False)
            # Afficher la section Machine
            self.machine_group.setVisible(calc_section_open)
            self.machine_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            # Masquer les contrôles liés aux consommables
            self._set_consumable_controls_visible(False, clear_selection=True)
        else:
            # Afficher les éléments standards
            self.subcategory_label.setVisible(True)
            self.subcategory_combo.setVisible(True)
            self.search_label.setVisible(True)
            self.search_field.setVisible(True)
            self.reset_search_button.setVisible(True)
            self.subsub_name_label.setVisible(True)
            self.subsub_name_combo.setVisible(True)
            self.year_combo.setVisible(True)
            self.input_label.setVisible(True)
            self.input_field.setVisible(True)
            self.calculate_button.setVisible(True)
            # Masquer la section Machine
            self.machine_group.setVisible(False)
            self.machine_group.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            # Le bloc consommable est affiché plus bas seulement pour Achats / Consommables.
            if category == 'Achats':
                self.subsub_name_label.setText('Code NACRES :')
            else:
                self.subsub_name_label.setText('Nom :')
            # Pour "Véhicules", afficher le champ "Nombre de jours"
            if category == 'Véhicules':
                self.days_label.setVisible(True)
                self.days_field.setVisible(True)
                self.days_field.setEnabled(True)
            else:
                self.days_label.setVisible(False)
                self.days_field.setVisible(False)
                self.days_field.setEnabled(False)
            # Mettre à jour la liste des sous-catégories en fonction de la catégorie
            subcats = self.data[self.data['category'] == category]['subcategory'].dropna().unique()
            self._populate_subcategory_combo(subcats.astype(str))
            self.update_subsubcategory_names()
            self.update_nacres_visibility()
        # existing_group contient aussi le sélecteur de catégorie : il doit rester
        # visible pour pouvoir quitter "Machine" et revenir vers Achats, Véhicules, etc.
        self.existing_group.setVisible(calc_section_open)
        self.machine_group.setVisible(calc_section_open and category == 'Machine')
        self._update_category_color()
        self.update_manage_consumable_button_state()
        self._update_field_indicators()

    def has_selected_consumable(self):
        if self.conso_filtered_combo is None or self.conso_filtered_combo.isHidden():
            return False
        return self._selected_consumable_data() is not None

    def update_manage_consumable_button_state(self):
        if not hasattr(self, "manage_consumables_button"):
            return
        can_manage = (
            self.consumable_actions_widget is not None
            and self.consumable_actions_widget.isVisible()
            and self.has_selected_consumable()
        )
        self.manage_consumables_button.setEnabled(can_manage)

    def update_nacres_visibility(self):
        """
        Met à jour la visibilité de la zone des consommables (NACRES).

        Affiche ou masque les éléments liés aux consommables en fonction de la catégorie sélectionnée.
        La zone est visible pour la sous-catégorie "Consommables", ainsi que pour un code NACRES
        d'une autre famille lorsqu'un consommable existe déjà pour ce code.
        """
        category = self.category_combo.currentText()
        subcat = self._current_subcategory()
        selected_prefix_has_consumables = (
            category == 'Achats' and
            self._nacres_prefix_has_consumables(self._selected_nacres_prefix())
        )

        if category == 'Achats' and subcat and (
            is_consumables_subcategory(subcat) or selected_prefix_has_consumables
        ):
            # On affiche la zone NACRES
            self._set_consumable_controls_visible(True)
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)
            self.fe_massique_label.setVisible(False)
            self.fe_massique_input.setVisible(False)
            self.origine_label.setVisible(False)
            self.origine_row_widget.setVisible(False)
            self.prix_unitaire_label.setVisible(False)
            self.prix_info_button.setVisible(False)
            self.masse_manquante_label.setVisible(False)
            self.contenant_warning_label.setVisible(False)
            # On met à jour la liste des consommables
            self.update_conso_filtered_combo()
        else:
            # On masque toute la zone consommables, y compris prix et masse.
            self._set_consumable_controls_visible(False, clear_selection=True)
        self.update_manage_consumable_button_state()

    def update_subsubcategory_names(self):
        """
        Met à jour les noms des sous-sous-catégories en fonction de la catégorie et sous-catégorie sélectionnées.

        Filtre les données en fonction des sélections actuelles, applique le filtre de recherche si nécessaire,
        et met à jour la combobox des noms. Ajoute également "non renseignée" comme option par défaut.
        """
        category = self.category_combo.currentText()
        subcategory = self._current_subcategory()
        search_text = normalize_search(self.search_field.text())

        global_achats_search = category == 'Achats' and bool(search_text)
        mask = (self.data['category'] == category)
        if subcategory and not global_achats_search:
            mask &= (self.data['subcategory'] == subcategory)

        filtered_data = self.data[mask]

        entries = []
        seen = set()

        def add_subsub_entry(row):
            subsubcategory = clean_text(row.get('subsubcategory', ''))
            name = clean_text(row.get('name', ''))
            display = clean_text(f"{subsubcategory} - {name}").strip(" - ")
            if not display:
                return
            haystack = normalize_search(display)
            if search_text and search_text not in haystack:
                return
            item_data = {
                "category": clean_text(row.get('category', '')),
                "subcategory": clean_text(row.get('subcategory', '')),
                "subsubcategory": subsubcategory,
                "name": name,
            }
            key = (
                item_data["category"],
                item_data["subcategory"],
                item_data["subsubcategory"],
                item_data["name"],
            )
            if key in seen:
                return
            seen.add(key)
            entries.append((display.casefold(), display, item_data))

        for _, row in filtered_data.iterrows():
            add_subsub_entry(row)

        if category == 'Achats' and subcategory and is_consumables_subcategory(subcategory):
            existing_prefixes = {
                normalize_nacres_prefix(data["subsubcategory"])
                for _, _, data in entries
                if normalize_nacres_prefix(data["subsubcategory"])
            }
            conso_filter = (
                self.conso_search_field.text()
                if self.conso_search_field is not None else None
            )
            available_prefixes = self._consumable_code_prefixes(
                filter_text=conso_filter or None
            )
            for prefix in sorted(available_prefixes - existing_prefixes):
                row = self._purchase_factor_row_for_nacres(prefix)
                if row is not None:
                    add_subsub_entry(row)

            existing_prefixes = {
                normalize_nacres_prefix(data["subsubcategory"])
                for _, _, data in entries
                if normalize_nacres_prefix(data["subsubcategory"])
            }
            conso_filter_norm = normalize_search(conso_filter) if conso_filter else None
            for option in self._nacres_options:
                if option.code in existing_prefixes:
                    continue
                purchase_row = self._purchase_factor_row_for_nacres(option.code)
                if purchase_row is not None:
                    subsubcategory = clean_text(purchase_row.get("subsubcategory", "")) or option.code
                    name = clean_text(purchase_row.get("name", "")) or option.label
                    item_subcategory = clean_text(purchase_row.get("subcategory", "")) or subcategory
                else:
                    subsubcategory = option.code
                    name = option.label
                    item_subcategory = subcategory
                display = f"{subsubcategory} - {name}".strip(" - ")
                haystack = normalize_search(display)
                if search_text and search_text not in haystack:
                    continue
                if conso_filter_norm and conso_filter_norm not in haystack:
                    continue
                item_data = {
                    "category": "Achats",
                    "subcategory": item_subcategory,
                    "subsubcategory": subsubcategory,
                    "name": name,
                    "nacres_status": option.statut_maj_2026,
                    "nacres_no_purchase_factor": not option.has_purchase_factor,
                    "nacres_new_without_fe": option.is_new_without_labo1point5_fe,
                }
                key = (
                    item_data["category"],
                    item_data["subcategory"],
                    item_data["subsubcategory"],
                    item_data["name"],
                )
                if key in seen:
                    continue
                seen.add(key)
                entries.append((display.casefold(), display, item_data))

        self.subsub_name_combo.blockSignals(True)
        self.subsub_name_combo.clear()
        self.subsub_name_combo.addItem("non renseignée")
        for _, display, item_data in sorted(entries):
            self.subsub_name_combo.addItem(display, userData=item_data)
            idx = self.subsub_name_combo.count() - 1
            if item_data.get("nacres_new_without_fe"):
                self.subsub_name_combo.setItemData(idx, _NACRES_NEW_NO_FE_COLOR, Qt.BackgroundRole)
                self.subsub_name_combo.setItemData(idx, _NACRES_NEW_NO_FE_TOOLTIP, Qt.ToolTipRole)
        self.subsub_name_combo.blockSignals(False)

        self.update_years()

    def update_years(self):
        """
        Met à jour la combobox des années disponibles en fonction de la sélection actuelle.

        Filtre les données en fonction de la catégorie, sous-catégorie, sous-sous-catégorie et nom sélectionnés,
        récupère les années disponibles et les ajoute à la combobox des années. Met à jour l'unité de mesure en conséquence.
        """
        category = self.category_combo.currentText()
        subcategory = self._current_subcategory()
        subsub_name = self.subsub_name_combo.currentText()
        item_data = self._current_subsub_data()
        if item_data:
            category = item_data.get("category", category)
            subcategory = item_data.get("subcategory", subcategory)
            subsubcategory = item_data.get("subsubcategory", "")
            name = item_data.get("name", "")
        else:
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
        subcategory = self._current_subcategory()
        subsub_name = self.subsub_name_combo.currentText()
        year = self.year_combo.currentText()
        item_data = self._current_subsub_data()
        if item_data:
            category = item_data.get("category", category)
            subcategory = item_data.get("subcategory", subcategory)
            subsubcategory = item_data.get("subsubcategory", "")
            name = item_data.get("name", "")
        else:
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
            # Le libellé "valeur journalière" n'est pertinent que si le champ "Nombre de jours" est affiché
            if self.days_label.isVisible():
                self.input_label.setText(f'Entrez la valeur journalière en {unit}:')
            elif category == "Achats" and is_consumables_subcategory(subcategory):
                self.input_label.setText(f'Montant en {unit}:')
            else:
                self.input_label.setText(f'Entrez la valeur en {unit}:')
            self.input_field.setEnabled(True)
        else:
            self.current_unit = None
            if item_data.get("nacres_new_without_fe"):
                self.input_label.setText(
                    "Aucun facteur d'émission GES 1point5 n'est défini pour cette nouvelle catégorie NACRES."
                )
            elif self.days_label.isVisible():
                self.input_label.setText('Entrez la valeur journalière:')
            else:
                self.input_label.setText('Entrez la valeur:')
            self.input_field.setEnabled(False)
        self.input_field.setToolTip(_NACRES_NEW_NO_FE_TOOLTIP if item_data.get("nacres_new_without_fe") else "")
        self._update_field_indicators()

    def update_conso_filtered_combo(self, filter_text=None):
        """
        Met à jour la combobox des consommables filtrés en fonction d'un texte de filtre.

        Remplit la combobox avec les consommables qui correspondent au texte de filtre saisi par l'utilisateur.
        Ajoute également "non renseignée" comme option par défaut. Bloque temporairement les signaux pour éviter des déclenchements intempestifs.
        
        Args:
            filter_text (str, optional): Le texte utilisé pour filtrer les consommables. Par défaut, None.
        """
        previous = self._selected_consumable_data()
        self.conso_filtered_combo.blockSignals(True)
        self.conso_filtered_combo.clear()
        self.conso_filtered_combo.addItem("non renseignée")

        if not isinstance(filter_text, str):
            filter_text = self.conso_search_field.text() if self.conso_search_field else ""
        filter_text = normalize_search(filter_text)

        entries = [
            (sort_key, full_code, consommable, source, packaging)
            for sort_key, full_code, consommable, source, search_text, _, packaging in self._consumable_search_entries
            if not filter_text or filter_text in search_text
        ]

        for _, code, name, source, packaging in sorted(entries):
            self._add_consumable_combo_item(code, name, source, packaging)

        self.conso_filtered_combo.blockSignals(False)
        if previous:
            self._select_consumable_item(
                previous["code_nacres"],
                previous["consommable"],
                previous.get("conditionnement", ""),
            )
        self.update_quantity_visibility()
        self.update_manage_consumable_button_state()

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
            self.fe_massique_label.setVisible(False)
            self.fe_massique_input.setVisible(False)
            self.origine_label.setVisible(False)
            self.origine_row_widget.setVisible(False)
            self.prix_unitaire_label.setToolTip("")
            self.prix_unitaire_label.setVisible(False)
            self.prix_info_button.setVisible(False)
            self.masse_manquante_label.setVisible(False)
            self.contenant_warning_label.setVisible(False)
            self._current_prix_unitaire = None
            self._current_prix_unitaire_info_text = ""
            self.update_manage_consumable_button_state()
            return

        self._sync_subcategory_from_subsub_selection()

        # Récupère les 4 premiers caractères comme code NACRES approximatif
        code_nacres_4 = self._selected_nacres_prefix() or normalize_nacres_prefix(subsub_name)
        can_show_consumables = (
            self.category_combo.currentText() == 'Achats' and
            (
                is_consumables_subcategory(self._current_subcategory()) or
                self._nacres_prefix_has_consumables(code_nacres_4)
            )
        )
        if not can_show_consumables:
            self._set_consumable_controls_visible(False, clear_selection=True)
            self.update_unit()
            self.update_manage_consumable_button_state()
            self._update_field_indicators()
            return

        filtered_items = [
            (sort_key, full_code, consommable, source, packaging)
            for sort_key, full_code, consommable, source, _, prefix, packaging in self._consumable_search_entries
            if prefix == code_nacres_4
        ]

        if not filtered_items:
            self.conso_filtered_combo.blockSignals(True)
            self.conso_filtered_combo.clear()
            self.conso_filtered_combo.addItem("non renseignée")
            self.conso_filtered_combo.blockSignals(False)
            for widget in (
                self.conso_filtered_label,
                self.indicator_conso,
                self.conso_filtered_combo,
                self.conso_search_label,
                self.conso_search_field,
                self.quantity_label,
                self.quantity_input,
                self.fe_massique_label,
                self.fe_massique_input,
                self.origine_label,
                self.origine_row_widget,
                self.prix_unitaire_label,
                self.prix_info_button,
                self.masse_manquante_label,
                self.contenant_warning_label,
                self.consumable_actions_widget,
            ):
                if widget is not None:
                    widget.setVisible(False)
            self._current_prix_unitaire = None
            self._current_prix_unitaire_info_text = ""
            self.prix_unitaire_label.setToolTip("")
            self.masse_manquante_label.setText("")
            self.contenant_warning_label.setText("")
            self.update_unit()
            self.update_manage_consumable_button_state()
            self._update_field_indicators()
            return

        for widget in (
            self.conso_filtered_label,
            self.conso_filtered_combo,
            self.conso_search_label,
            self.conso_search_field,
            self.consumable_actions_widget,
        ):
            if widget is not None:
                widget.setVisible(True)
        self.conso_filtered_combo.blockSignals(True)
        self.conso_filtered_combo.clear()
        self._add_direct_nacres_combo_item(code_nacres_4)
        for _, code, name, source, packaging in sorted(filtered_items):
            self._add_consumable_combo_item(code, name, source, packaging)
        self.conso_filtered_combo.blockSignals(False)

        if len(filtered_items) == 1:
            self.conso_filtered_combo.setCurrentIndex(1)
        else:
            self.conso_filtered_combo.setCurrentIndex(0)

        if self._selected_consumable_data() is None:
            self.on_conso_filtered_changed()
        else:
            self.update_quantity_visibility()
            self.update_unit()
            self._update_field_indicators()
        self.update_manage_consumable_button_state()

    def on_conso_filtered_changed(self):
        """
        Gère l'événement de changement de sélection dans la combobox des consommables filtrés.

        Met à jour la catégorie à 'Achats' si nécessaire, sélectionne la sous-catégorie réelle
        du code NACRES, et ajuste la sélection des sous-sous-catégories en fonction du consommable sélectionné.
        Affiche la barre "Quantité" si un consommable valide est sélectionné.
        """
        # Réinitialiser les champs de valeur à chaque changement de consommable
        for field in (self.input_field, self.quantity_input):
            if field is not None:
                field.blockSignals(True)
                field.clear()
                field.blockSignals(False)

        selected = self._selected_consumable_data()
        if not selected:
            has_nacres_code = bool(self._selected_nacres_prefix())
            self.update_manage_consumable_button_state()
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)
            self.fe_massique_label.setVisible(False)
            self.fe_massique_input.setVisible(False)
            self.origine_label.setVisible(False)
            self.origine_row_widget.setVisible(False)
            self._current_prix_unitaire = None
            self._current_prix_unitaire_info_text = ""
            self.prix_unitaire_label.setToolTip("")
            self.prix_unitaire_label.setVisible(False)
            self.prix_info_button.setVisible(False)
            self.masse_manquante_label.setVisible(False)
            self.contenant_warning_label.setVisible(False)
            if not has_nacres_code:
                # Aucune sélection exploitable : on revient à l'état vide.
                self.subsub_name_combo.blockSignals(True)
                idx_nr = self.subsub_name_combo.findText("non renseignée")
                if idx_nr != -1:
                    self.subsub_name_combo.setCurrentIndex(idx_nr)
                else:
                    self.subsub_name_combo.setCurrentIndex(0)
                self.subsub_name_combo.blockSignals(False)
            self.update_unit()
            self._update_field_indicators()
            return

        # Récupérer codeNACRES_4
        code_nacres_4 = normalize_nacres_prefix(selected["code_nacres"])

        # Forcer la catégorie Achats.
        was_achats = self.category_combo.currentText() == "Achats"
        idx_cat = self.category_combo.findText("Achats")
        if idx_cat >= 0:
            self.category_combo.blockSignals(True)
            self.category_combo.setCurrentIndex(idx_cat)
            self.category_combo.blockSignals(False)
            if not was_achats:
                subcats = self.data[self.data['category'] == "Achats"]['subcategory'].dropna().unique()
                self._populate_subcategory_combo(subcats.astype(str))

        purchase_row = self._purchase_factor_row_for_nacres(
            code_nacres_4,
            preferred_subcategory=self._current_subcategory(),
        )
        target_subcat = (
            clean_text(purchase_row.get("subcategory", ""))
            if purchase_row is not None else
            None
        )
        if not target_subcat:
            for i in range(self.subcategory_combo.count()):
                txt = clean_text(self.subcategory_combo.itemData(i)) or self.subcategory_combo.itemText(i)
                if is_consumables_subcategory(txt):
                    target_subcat = txt
                    break
        if target_subcat is not None:
            self.subcategory_combo.blockSignals(True)
            self._select_subcategory(target_subcat)
            self.subcategory_combo.blockSignals(False)

        # On appelle update_subsubcategory_names() après avoir ciblé la sous-catégorie réelle
        # du code NACRES. AA01, par exemple, garde ainsi son facteur monétaire d'origine.
        self.update_subsubcategory_names()

        if purchase_row is None:
            # subsub => "non renseignée"
            self.subsub_name_combo.blockSignals(True)
            idx_nr = self.subsub_name_combo.findText("non renseignée")
            if idx_nr != -1:
                self.subsub_name_combo.setCurrentIndex(idx_nr)
            else:
                self.subsub_name_combo.setCurrentIndex(0)
            self.subsub_name_combo.blockSignals(False)
        else:
            real_subsub = clean_text(purchase_row.get('subsubcategory', ''))
            real_name = clean_text(purchase_row.get('name', ''))
            new_subsub_text = f"{real_subsub} - {real_name}".strip(" - ")
            item_data = {
                "category": "Achats",
                "subcategory": clean_text(purchase_row.get('subcategory', '')),
                "subsubcategory": real_subsub,
                "name": real_name,
            }

            self.subsub_name_combo.blockSignals(True)
            idx_ss = self.subsub_name_combo.findText(new_subsub_text)
            if idx_ss != -1:
                self.subsub_name_combo.setCurrentIndex(idx_ss)
            else:
                # On ajoute
                self.subsub_name_combo.addItem(new_subsub_text, userData=item_data)
                self.subsub_name_combo.setCurrentIndex(self.subsub_name_combo.count() - 1)
            self.subsub_name_combo.blockSignals(False)

        self._update_quantity_label(selected)
        self.quantity_label.setVisible(True)
        self.quantity_input.setVisible(True)
        show_origin = self._should_show_origin_selector(selected)
        self.origine_label.setVisible(show_origin)
        self.origine_row_widget.setVisible(show_origin)

        self.update_unit()
        self._update_prix_unitaire()
        self._update_masse_warning()
        self.update_manage_consumable_button_state()

    def _update_prix_unitaire(self):
        """
        Met à jour le label de prix unitaire en fonction du consommable sélectionné.
        Si un prix est trouvé dans le catalogue IJM, affiche le prix et stocke la valeur.
        """
        selected = self._selected_consumable_data()
        if not selected:
            self._current_prix_unitaire = None
            self._current_prix_unitaire_info_text = ""
            self.prix_unitaire_label.setToolTip("")
            self.prix_unitaire_label.setVisible(False)
            self.prix_info_button.setVisible(False)
            return

        code_nacres_full = selected["code_nacres"]
        consommable_name = selected["consommable"]
        conditionnement = selected.get("conditionnement", "")

        prix_info = self.data_manager.get_prix_unitaire_info(
            code_nacres_full.strip(),
            consommable_name,
            conditionnement,
        )
        if prix_info and prix_info.get("prix_unitaire") is not None:
            prix = prix_info["prix_unitaire"]
            self._current_prix_unitaire = prix
            price_source = str(prix_info.get("source_catalogue") or "").strip()
            source_label = "catalogue IJM" if price_source else "base consommables"
            nb_unites = prix_info.get("nb_unites", "")
            try:
                nb_val = int(float(nb_unites)) if nb_unites not in ("", None) else None
            except (ValueError, TypeError):
                nb_val = None
            if nb_val and nb_val > 1:
                label_text = (
                    f"ℹ  Prix par unité vendue ({source_label}) : {prix:.4f} €  |  "
                    f"Conditionnement : {nb_val} unités"
                )
            else:
                label_text = f"ℹ  Prix par unité vendue ({source_label}) : {prix:.4f} €"
            self.prix_unitaire_label.setText(label_text)
            self._current_prix_unitaire_info_text = self._format_prix_unitaire_tooltip(prix_info)
            self.prix_unitaire_label.setToolTip(self._current_prix_unitaire_info_text)
            self.prix_unitaire_label.setToolTipDuration(20000)
            self.prix_unitaire_label.setStyleSheet(
                "color: #1e40af; background-color: #eff6ff; "
                "border: 1px solid #bfdbfe; border-radius: 4px; padding: 4px 8px;"
            )
            self.prix_unitaire_label.setVisible(True)
            self.prix_info_button.setVisible(True)
        else:
            self._current_prix_unitaire = None
            self._current_prix_unitaire_info_text = ""
            self.prix_unitaire_label.setToolTip("")
            self.prix_unitaire_label.setVisible(False)
            self.prix_info_button.setVisible(False)

    def show_prix_unitaire_info(self):
        """Affiche immédiatement le détail du prix IJM associé au consommable."""
        if not self._current_prix_unitaire_info_text:
            return

        QToolTip.showText(
            QCursor.pos(),
            self._current_prix_unitaire_info_text,
            self.prix_info_button,
            self.prix_info_button.rect(),
            20000,
        )

    def _update_origine_info_button(self):
        if self.origine_info_button is not None:
            self.origine_info_button.setEnabled(self.origine_combo is not None and self.origine_combo.count() > 0)

    def show_origine_info(self):
        """Affiche les détails du facteur de transport pour la provenance sélectionnée."""
        if self.origine_combo is None:
            return
        origine = self.origine_combo.currentText()
        factor, uncert = self.data_manager.get_transport_factor(origine)

        df = self.data_manager.data_transport
        row = None
        if not df.empty:
            mask = df[self.data_manager.TRANSPORT_ORIGINE_COL] == origine
            if mask.any():
                row = df[mask].iloc[0]

        lines = [f"Provenance : {origine}"]
        if row is not None:
            dist = int(row.get("Distance (km)", 0))
            mode = row.get("Mode", "")
            source = row.get("Source", "")
            lines.append(f"Distance évaluée : {dist:,} km".replace(",", " "))
            lines.append(f"Mode : {mode}")
            lines.append(f"Facteur transport : {factor:.3f} kg CO₂e/kg")
            lines.append(f"Incertitude : ±{int(uncert * 100)} %")
            lines.append(f"Source : {source}")
        else:
            lines.append(f"Facteur transport : {factor:.3f} kg CO₂e/kg")
            lines.append(f"Incertitude : ±{int(uncert * 100)} %")

        if origine == self.data_manager.TRANSPORT_DEFAULT:
            lines.append("")
            lines.append("Valeur par défaut : moyenne entre USA (0,18) et Asie (0,35)")
            lines.append("par fret maritime. S'applique si l'origine est inconnue.")

        QToolTip.showText(
            QCursor.pos(),
            "\n".join(lines),
            self.origine_info_button,
            self.origine_info_button.rect(),
            20000,
        )

    def _format_prix_unitaire_tooltip(self, prix_info):
        """Construit l'infobulle de détail du prix utilisé."""
        source_catalogue = str(prix_info.get("source_catalogue") or "").strip()
        lines = [
            "Produit catalogue IJM utilisé pour le prix :"
            if source_catalogue else
            "Prix renseigné dans la base consommables :"
        ]
        fields = [
            ("Désignation", prix_info.get("designation")),
            ("Code IJM", prix_info.get("code_ijm")),
            ("Marque", prix_info.get("marque")),
            ("Prix HT du conditionnement vendu", prix_info.get("prix_ht")),
            ("Conditionnement vendu", prix_info.get("conditionnement")),
            ("Unités par conditionnement vendu", prix_info.get("nb_unites")),
            ("Prix par unité vendue", prix_info.get("prix_unitaire")),
            ("Source catalogue", source_catalogue),
            ("Validation", prix_info.get("validation")),
            ("Score de rapprochement", prix_info.get("score_match")),
        ]

        for label, value in fields:
            value_text = str(value or "").strip()
            if value_text and value_text.lower() != "nan":
                if label == "Prix par unité vendue":
                    try:
                        value_text = f"{float(value):.4f} €"
                    except (TypeError, ValueError):
                        pass
                elif label == "Prix HT du conditionnement vendu":
                    try:
                        value_text = f"{float(value):.2f} €"
                    except (TypeError, ValueError):
                        pass
                lines.append(f"{label} : {value_text}")

        score_text = str(prix_info.get("score_match") or "").strip()
        try:
            score = float(score_text)
        except ValueError:
            score = None
        if score is not None and score < 0.55:
            lines.append("")
            lines.append("Attention : rapprochement catalogue approximatif, à vérifier.")

        return "\n".join(lines)

    def _update_category_color(self):
        if self.category_color_dot is None or self.category_combo is None:
            return
        color = CATEGORY_COLORS.get(self.category_combo.currentText(), '#888888')
        self.category_color_dot.setStyleSheet(f"background-color: {color}; border-radius: 6px;")

    def _update_graph_buttons_state(self, *_):
        has_data = self.history_list is not None and self.history_list.rowCount() > 0
        for btn in (
            self.generate_pie_button,
            self.generate_bar_button,
            self.generate_proportional_bar_button,
            self.generate_stacked_bar_consumables_button,
            self.generate_nacres_bar_button,
            self.generate_proportional_bar_button_mass,
            self.generate_pareto_button,
            self.generate_transport_consumable_button,
            self.generate_transport_top_button,
            self.generate_transport_button,
            self.generate_transport_factor_button,
            self.generate_transport_scenario_button,
            self.generate_coverage_button,
            self.generate_coverage_category_button,
            self.summary_pdf_button,
        ):
            if btn is not None:
                btn.setEnabled(has_data)

    def _update_history_buttons_state(self, *_):
        if self.history_list is None or self.delete_button is None or self.modify_button is None:
            return
        has_rows = self.history_list.rowCount() > 0
        has_selection = bool(self.history_list.selectionModel().selectedRows())
        self.delete_button.setEnabled(has_selection)
        self.modify_button.setEnabled(has_selection)
        if self.create_user_manip_button is not None:
            self.create_user_manip_button.setEnabled(has_rows)

    _STYLE_RESULT_OK = (
        "QLabel { background-color: #eef4fb; border: 1px solid #93c5e8; border-radius: 6px;"
        " padding: 8px 12px; font-size: 12px; color: #17415f; font-weight: 500; }"
    )
    _STYLE_RESULT_ERR = (
        "QLabel { background-color: #fef2f2; border: 1px solid #fca5a5; border-radius: 6px;"
        " padding: 8px 12px; font-size: 12px; color: #991b1b; font-weight: 500; }"
    )

    def _result_show_ok(self, html):
        if self.result_area is None:
            return
        self.result_area.setStyleSheet(self._STYLE_RESULT_OK)
        self.result_area.setText(html)

    def _result_show_error(self, text):
        if self.result_area is None:
            return
        self.result_area.setStyleSheet(self._STYLE_RESULT_ERR)
        self.result_area.setText(text)

    def _set_indicator(self, label, ok):
        if label is None:
            return
        if ok:
            label.setText("✔")
            label.setStyleSheet("color: #16a34a; font-size: 15px; font-weight: bold;")
        else:
            label.setText("✗")
            label.setStyleSheet("color: #dc2626; font-size: 15px; font-weight: bold;")

    def _update_field_indicators(self):
        if self.indicator_nacres is None:
            return
        category = self.category_combo.currentText() if self.category_combo else ""

        # NACRES indicator: valid when subsub_name_combo is not "non renseignée" and is visible
        nacres_visible = (
            self.subsub_name_combo is not None
            and self.subsub_name_combo.isVisible()
            and category != "Machine"
        )
        if nacres_visible:
            subsub_ok = (
                self.subsub_name_combo.currentText()
                and self.subsub_name_combo.currentText() != "non renseignée"
            )
            self._set_indicator(self.indicator_nacres, subsub_ok)
            self.indicator_nacres.setVisible(True)
        else:
            self.indicator_nacres.setVisible(False)

        # Consommable indicator: valid when conso_filtered_combo is visible and not "non renseignée"
        conso_visible = (
            self.conso_filtered_combo is not None
            and self.conso_filtered_combo.isVisible()
        )
        if conso_visible:
            conso_ok = self._selected_consumable_data() is not None or bool(self._selected_nacres_prefix())
            self._set_indicator(self.indicator_conso, conso_ok)
            self.indicator_conso.setVisible(True)
        else:
            self.indicator_conso.setVisible(False)

        # input_field border: green when filled and enabled, red when empty and enabled
        if self.input_field is not None and self.input_field.isVisible():
            if not self.input_field.isEnabled():
                self.input_field.setStyleSheet("")
            elif self.input_field.text().strip():
                self.input_field.setStyleSheet(
                    "border: 1.5px solid #86efac; border-radius: 3px;"
                )
            else:
                self.input_field.setStyleSheet(
                    "border: 1.5px solid #fca5a5; border-radius: 3px;"
                )

        # quantity_input border
        if self.quantity_input is not None and self.quantity_input.isVisible():
            if self.quantity_input.text().strip():
                self.quantity_input.setStyleSheet(
                    "border: 1.5px solid #86efac; border-radius: 3px;"
                )
            else:
                self.quantity_input.setStyleSheet(
                    "border: 1.5px solid #fca5a5; border-radius: 3px;"
                )

    def _consumable_has_mass_data(self, selected):
        """Retourne True si le consommable sélectionné a des données de masse (solide ou liquide)."""
        import pandas as pd
        if not selected:
            return False
        if selected.get("source") == "liquid":
            return True
        solid_row = self._find_consumable_mass_row(
            selected["code_nacres"],
            selected["consommable"],
            selected.get("conditionnement", ""),
        )
        if solid_row is None:
            return False
        if self._solid_row_liquid_factor(solid_row) is not None:
            return True
        masse = solid_row.get(self.data_manager.MASSE_G_COL, "")
        return not (pd.isna(masse) or str(masse).strip() == "")

    def _should_show_origin_selector(self, selected):
        """Demande la provenance dès qu'un consommable est sélectionné.

        La provenance reste utile même si les données de masse sont incomplètes :
        elle est conservée dans l'historique, et le calcul transport s'active dès
        qu'une masse exploitable existe.
        """
        return selected is not None

    def _solid_row_liquid_factor(self, solid_row):
        factor_col = getattr(self.data_manager, "FACTEUR_LIQUIDE_SOURCE_COL", "Facteur liquide source")
        factor_name = clean_text(solid_row.get(factor_col, ""))
        if not factor_name:
            return None
        return self.data_manager.get_liquid_data(
            solid_row.get(self.data_manager.CODE_NACRES_COL, ""),
            factor_name,
        )

    def _is_solid_liquid_product(self, solid_row):
        return looks_like_liquid_commercial_product(
            solid_row,
            factor_col=getattr(self.data_manager, "FACTEUR_LIQUIDE_SOURCE_COL", "Facteur liquide source"),
            unit_col=getattr(self.data_manager, "UNITE_LIQUIDE_COL", "Unité liquide"),
            volume_col=getattr(self.data_manager, "VOLUME_FLACON_COL", "Volume flacon (mL)"),
            name_col=getattr(self.data_manager, "CONSOMMABLE_COL", "Consommable"),
            code_col=getattr(self.data_manager, "CODE_NACRES_COL", "Code NACRES"),
        )

    def _update_masse_warning(self):
        """
        Affiche un avertissement si le consommable sélectionné n'a pas
        de données de masse enregistrées dans la base.
        """
        import pandas as pd

        def _missing_text(value):
            text = clean_text(value)
            return not text or text.casefold() in {"na", "n/a"}

        selected = self._selected_consumable_data()
        if not selected:
            self.masse_manquante_label.setVisible(False)
            self.contenant_warning_label.setVisible(False)
            return

        if selected.get("source") == "liquid":
            liq_row = self.data_manager.get_liquid_data(
                selected.get("code_nacres", ""),
                selected.get("consommable", ""),
                selected.get("conditionnement", ""),
            )
            unit = clean_text(liq_row.get("Unité", "") if liq_row is not None else "").casefold()
            is_volume_based = unit in {"ml", "millilitre", "millilitres"} or (
                liq_row is not None and safe_float(liq_row.get("Volume flacon (mL)", 0.0), default=0.0) > 0
            )
            has_container = (
                liq_row is not None and
                not _missing_text(liq_row.get("Matériau contenant", "")) and
                safe_float(liq_row.get("Masse contenant (g)", 0.0), default=0.0) > 0
            )
            self.masse_manquante_label.setText(
                "✔  Données liquide/solvant disponibles." if is_volume_based
                else "✔  Données consommable disponibles."
            )
            self.masse_manquante_label.setStyleSheet(
                "color: #166534; background-color: #dcfce7; "
                "border: 1px solid #86efac; border-radius: 4px; padding: 4px 8px;"
            )
            self.masse_manquante_label.setVisible(True)
            if is_volume_based and not has_container:
                self.contenant_warning_label.setText(
                    "⚠  Contenant/flacon non renseigné. Cliquez sur « Enrichir » pour ajouter "
                    "le matériau et la masse du contenant : cela peut modifier significativement le résultat."
                )
                self.contenant_warning_label.setStyleSheet(
                    "color: #92400e; background-color: #fffbeb; "
                    "border: 1px solid #fcd34d; border-radius: 4px; padding: 4px 8px;"
                )
                self.contenant_warning_label.setVisible(True)
            else:
                self.contenant_warning_label.setVisible(False)
            return

        self.contenant_warning_label.setVisible(False)

        solid_row = self._find_consumable_mass_row(
            selected["code_nacres"],
            selected["consommable"],
            selected.get("conditionnement", ""),
        )
        if solid_row is None:
            self.masse_manquante_label.setText(
                "⚠  Masse non enregistrée pour ce consommable : le calcul CO₂ sera incomplet."
            )
            self.masse_manquante_label.setStyleSheet(
                "color: #92400e; background-color: #fef3c7; "
                "border: 1px solid #f59e0b; border-radius: 4px; padding: 4px 8px;"
            )
            self.masse_manquante_label.setVisible(True)
            return
        if self._is_solid_liquid_product(solid_row):
            factor_row = self._solid_row_liquid_factor(solid_row)
            factor_name = clean_text(solid_row.get(
                getattr(self.data_manager, "FACTEUR_LIQUIDE_SOURCE_COL", "Facteur liquide source"),
                ""
            ))
            if factor_row is not None:
                self.masse_manquante_label.setText(
                    f"✔  Facteur liquide/solvant disponible : {factor_name}."
                )
                self.masse_manquante_label.setStyleSheet(
                    "color: #166534; background-color: #dcfce7; "
                    "border: 1px solid #86efac; border-radius: 4px; padding: 4px 8px;"
                )
            else:
                self.masse_manquante_label.setText(
                    "⚠  Aucun facteur liquide/solvant lié — renseignez un facteur d'émission ou enrichissez le consommable."
                )
                self.masse_manquante_label.setStyleSheet(
                    "color: #92400e; background-color: #fef3c7; "
                    "border: 1px solid #f59e0b; border-radius: 4px; padding: 4px 8px;"
                )
            self.masse_manquante_label.setVisible(True)

            has_container = (
                not _missing_text(solid_row.get(self.data_manager.MATERIAU_CONDITIONNEMENT_COL, "")) and
                safe_float(solid_row.get(self.data_manager.MASSE_CONDITIONNEMENT_COL, 0.0), default=0.0) > 0
            )
            if not has_container:
                self.contenant_warning_label.setText(
                    "⚠  Contenant/flacon non renseigné. Cliquez sur « Enrichir » pour ajouter "
                    "le matériau et la masse du contenant : cela peut modifier significativement le résultat."
                )
                self.contenant_warning_label.setStyleSheet(
                    "color: #92400e; background-color: #fffbeb; "
                    "border: 1px solid #fcd34d; border-radius: 4px; padding: 4px 8px;"
                )
                self.contenant_warning_label.setVisible(True)
            else:
                self.contenant_warning_label.setVisible(False)
            return

        masse = solid_row.get(self.data_manager.MASSE_G_COL, "")
        materiau = str(solid_row.get(self.data_manager.MATERIAU_COL, "") or "").strip()
        if pd.isna(masse) or str(masse).strip() == "":
            self.masse_manquante_label.setText(
                "⚠  Masse non enregistrée pour ce consommable : le calcul CO₂ sera incomplet."
            )
            self.masse_manquante_label.setStyleSheet(
                "color: #92400e; background-color: #fef3c7; "
                "border: 1px solid #f59e0b; border-radius: 4px; padding: 4px 8px;"
            )
        elif not materiau:
            self.masse_manquante_label.setText(
                "⚠  Matériau du produit non disponible : calcul du eCO₂ par la masse non disponible."
            )
            self.masse_manquante_label.setStyleSheet(
                "color: #92400e; background-color: #fef3c7; "
                "border: 1px solid #f59e0b; border-radius: 4px; padding: 4px 8px;"
            )
        else:
            self.masse_manquante_label.setText(
                "✔  Masse disponible : calcul eCO₂ par la masse effectué."
            )
            self.masse_manquante_label.setStyleSheet(
                "color: #166534; background-color: #dcfce7; "
                "border: 1px solid #86efac; border-radius: 4px; padding: 4px 8px;"
            )
        self.masse_manquante_label.setVisible(True)

        has_packaging = (
            not _missing_text(solid_row.get(self.data_manager.MATERIAU_EMBALLAGE_COL, "")) and
            safe_float(solid_row.get(self.data_manager.MASSE_EMBALLAGE_COL, 0.0), default=0.0) > 0
        )
        if not has_packaging:
            self.contenant_warning_label.setText(
                "⚠  Emballage secondaire non renseigné. Cliquez sur « Enrichir » pour ajouter "
                "le matériau et la masse de l'emballage secondaire : cela peut modifier significativement le résultat."
            )
            self.contenant_warning_label.setStyleSheet(
                "color: #92400e; background-color: #fffbeb; "
                "border: 1px solid #fcd34d; border-radius: 4px; padding: 4px 8px;"
            )
            self.contenant_warning_label.setVisible(True)
        else:
            self.contenant_warning_label.setVisible(False)

    def _liquid_conditionnement_quantity(self, row, unit):
        """Quantité contenue dans une unité vendue, exprimée dans l'unité de saisie."""
        unit_clean = clean_text(unit).casefold() or "ml"
        condt = clean_text(row.get("condt_ijm", "")).casefold().replace(",", ".")

        if unit_clean in {"ml", "millilitre", "millilitres"}:
            volume = safe_float(row.get("Volume flacon (mL)", None), default=0.0)
            if volume > 0:
                return volume
            match_ml = re.search(r"(\d+(?:\.\d+)?)\s*ml\b", condt)
            if match_ml:
                return safe_float(match_ml.group(1), default=0.0)
            match_l = re.search(r"(\d+(?:\.\d+)?)\s*(?:l|litre|liter)s?\b", condt)
            if match_l:
                return safe_float(match_l.group(1), default=0.0) * 1000.0
            return 0.0

        if unit_clean in {"g", "gramme", "grammes"}:
            match_kg = re.search(r"(\d+(?:\.\d+)?)\s*kg\b", condt)
            if match_kg:
                return safe_float(match_kg.group(1), default=0.0) * 1000.0
            match_g = re.search(r"(\d+(?:\.\d+)?)\s*g\b", condt)
            if match_g:
                return safe_float(match_g.group(1), default=0.0)
            return 0.0

        if unit_clean in {"kg", "kilogramme", "kilogrammes"}:
            match_kg = re.search(r"(\d+(?:\.\d+)?)\s*kg\b", condt)
            if match_kg:
                return safe_float(match_kg.group(1), default=0.0)
            match_g = re.search(r"(\d+(?:\.\d+)?)\s*g\b", condt)
            if match_g:
                return safe_float(match_g.group(1), default=0.0) / 1000.0
            return 0.0

        return 0.0

    def _auto_fill_prix(self):
        """
        Remplit automatiquement le champ prix (input_field).
        - Solides : quantité (unités) × prix unitaire IJM
        - Liquides : quantité / quantité de l'unité vendue × prix de l'unité IJM
        """
        if self._current_prix_unitaire is None:
            return
        qty_str = self.quantity_input.text().strip().replace(',', '.')
        if not qty_str:
            return
        try:
            qty = float(qty_str)
        except ValueError:
            return

        selected = self._selected_consumable_data()
        if selected and selected.get("source") == "liquid":
            row = self.data_manager.get_liquid_data(
                selected.get("code_nacres", ""),
                selected.get("consommable", ""),
                selected.get("conditionnement", ""),
            )
            if row is None:
                return
            unit = clean_text(row.get("Unité", "")) or "mL"
            conditionnement_qty = self._liquid_conditionnement_quantity(row, unit)
            if conditionnement_qty <= 0:
                return
            prix_total = (qty / conditionnement_qty) * self._current_prix_unitaire
        elif selected:
            solid_row = self._find_consumable_mass_row(
                selected.get("code_nacres", ""),
                selected.get("consommable", ""),
                selected.get("conditionnement", ""),
            )
            if solid_row is not None and self._is_solid_liquid_product(solid_row):
                unit = clean_text(solid_row.get(getattr(self.data_manager, "UNITE_LIQUIDE_COL", "Unité liquide"), "")) or "mL"
                conditionnement_qty = self._liquid_conditionnement_quantity(solid_row, unit)
                if conditionnement_qty <= 0:
                    return
                prix_total = (qty / conditionnement_qty) * self._current_prix_unitaire
            elif self._current_masse_unitaire_g and self._current_masse_unitaire_g > 0:
                # Solide vendu en vrac : qty est en grammes
                prix_total = (qty / self._current_masse_unitaire_g) * self._current_prix_unitaire
            else:
                prix_total = qty * self._current_prix_unitaire
        else:
            prix_total = qty * self._current_prix_unitaire

        self.input_field.blockSignals(True)
        self.input_field.setText(f"{prix_total:.2f}")
        self.input_field.blockSignals(False)

    def _get_masse_unitaire_g(self, selected):
        """Retourne la masse unitaire (g) pour mode vrac, ou 0 si discret/non défini.

        Mode vrac = masse renseignée ET matériau non défini (produit en vrac, poudre...).
        Si matériau défini = objet discret dont la masse sert au calcul CO₂ interne.
        """
        if not selected or selected.get("source") == "liquid":
            return 0.0
        code = selected.get("code_nacres", "")
        name = selected.get("consommable", "")
        row = self._find_consumable_mass_row(code, name, selected.get("conditionnement", ""))
        if row is None:
            return 0.0
        if self._is_solid_liquid_product(row):
            return 0.0
        materiau = str(row.get(self.data_manager.MATERIAU_COL, "") or "").strip()
        if materiau:
            return 0.0  # Objet discret avec matériau connu — pas de mode vrac
        return safe_float(row.get(self.data_manager.MASSE_G_COL, 0.0))

    def _liquid_has_co2_factor(self, selected):
        """Retourne True si le consommable liquide a un facteur CO₂ défini dans la base."""
        if selected.get("source") == "solid":
            solid_row = self._find_consumable_mass_row(
                selected.get("code_nacres", ""),
                selected.get("consommable", ""),
                selected.get("conditionnement", ""),
            )
            row = self._solid_row_liquid_factor(solid_row) if solid_row is not None else None
        else:
            row = self.data_manager.get_liquid_data(
                selected.get("code_nacres", ""),
                selected.get("consommable", ""),
                selected.get("conditionnement", ""),
            )
        if row is None:
            return False
        return safe_float(row.get("Facteur CO₂ (kg CO₂e/kg)", 0.0), default=0.0) > 0

    def _update_quantity_label(self, selected):
        """Met à jour le texte du label Quantité et le champ FE selon le type de consommable."""
        source = selected.get("source", "solid") if selected else "solid"
        if source == "liquid":
            row = self.data_manager.get_liquid_data(
                selected.get("code_nacres", ""),
                selected.get("consommable", ""),
                selected.get("conditionnement", ""),
            )
            unit = "mL"
            if row is not None:
                u = str(row.get("Unité", "") or "").strip()
                if u:
                    unit = u
            self._current_masse_unitaire_g = None
            self.quantity_label.setText(f"Quantité ({unit}) :")
            has_factor = self._liquid_has_co2_factor(selected)
            if clean_text(unit).casefold() in {"g", "kg", "gramme", "grammes", "kilogramme", "kilogrammes"}:
                self.fe_massique_label.setText("Facteur d'émission (kg eCO₂/kg) :")
            else:
                self.fe_massique_label.setText("Facteur d'émission (kg eCO₂/L) :")
            self.fe_massique_label.setVisible(not has_factor)
            self.fe_massique_input.setVisible(not has_factor)
        else:
            solid_row = self._find_consumable_mass_row(
                selected.get("code_nacres", ""),
                selected.get("consommable", ""),
                selected.get("conditionnement", ""),
            )
            if solid_row is not None and self._is_solid_liquid_product(solid_row):
                unit = clean_text(solid_row.get(getattr(self.data_manager, "UNITE_LIQUIDE_COL", "Unité liquide"), "")) or "mL"
                self._current_masse_unitaire_g = None
                self.quantity_label.setText(f"Quantité ({unit}) :")
                has_factor = self._liquid_has_co2_factor(selected)
                self.fe_massique_label.setText("Facteur d'émission (kg eCO₂/L) :")
                self.fe_massique_label.setVisible(not has_factor)
                self.fe_massique_input.setVisible(not has_factor)
                return
            masse_g = self._get_masse_unitaire_g(selected)
            if masse_g and masse_g > 0:
                self._current_masse_unitaire_g = masse_g
                self.quantity_label.setText("Quantité (g) :")
            else:
                self._current_masse_unitaire_g = None
                self.quantity_label.setText("Quantité (unités) :")
            self.fe_massique_label.setVisible(False)
            self.fe_massique_input.setVisible(False)

    def update_quantity_visibility(self):
        """
        Met à jour la visibilité de la barre "Quantité" en fonction de la catégorie sélectionnée et du consommable.

        Affiche la barre "Quantité" uniquement si la catégorie est 'Achats' et qu'un consommable valide est sélectionné.
        Pour toutes les autres catégories, la barre "Quantité" reste masquée.
        """
        category = self.category_combo.currentText()

        if category != 'Achats':
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)
        else:
            selected = self._selected_consumable_data()
            if selected is None:
                self.quantity_label.setVisible(False)
                self.quantity_input.setVisible(False)
            else:
                self._update_quantity_label(selected)
                self.quantity_label.setVisible(True)
                self.quantity_input.setVisible(True)

    def split_subsub_name(self, subsub_name):
        """
        Sépare une chaîne "subsubcategory - name" en un tuple (subsubcategory, name).
        Si le séparateur ' - ' est absent, retourne ('', subsub_name).
        """
        if ' - ' in subsub_name:
            subsub, name = subsub_name.split(' - ', 1)
        else:
            subsub, name = '', subsub_name
        return subsub.strip(), name.strip()
    
    def _raise_existing_data_mass_window(self):
        """Ramène au premier plan la fenêtre déjà ouverte. Retourne True si elle existait."""
        if (
            self.data_mass_window is not None
            and isValid(self.data_mass_window)
            and self.data_mass_window.isVisible()
        ):
            self.data_mass_window.raise_()
            self.data_mass_window.activateWindow()
            return True
        return False

    def open_data_mass_window(self):
        """Ouvre la fenêtre de gestion pré-remplie avec le consommable sélectionné."""
        if self._raise_existing_data_mass_window():
            return
        if not self.has_selected_consumable():
            return

        selected = self._selected_consumable_data()
        prefill_code, prefill_name, prefill_source = None, None, "solid"
        if selected:
            prefill_code = selected["code_nacres"]
            prefill_name = selected["consommable"]
            prefill_source = selected.get("source", "solid")

        self.data_mass_window = DataMassWindow(
            parent=self,
            data_materials=self.data_materials,
            base_path=self.data_manager.base_path,
            user_path=self.data_manager.user_path,
            mode_filter="consumable",
            prefill_code=prefill_code,
            prefill_name=prefill_name,
            prefill_source=prefill_source,
            sqlite_path=getattr(self.data_manager, "sqlite_path", None),
        )
        self.data_mass_window.data_added.connect(self._reload_consumables_data)
        self.data_mass_window.show()

    def open_data_mass_window_new(self):
        """Ouvre la fenêtre de gestion avec le formulaire vierge pour ajouter un nouveau consommable."""
        if self._raise_existing_data_mass_window():
            return
        self.data_mass_window = DataMassWindow(
            parent=self,
            data_materials=self.data_materials,
            base_path=self.data_manager.base_path,
            user_path=self.data_manager.user_path,
            mode_filter="consumable",
            sqlite_path=getattr(self.data_manager, "sqlite_path", None),
        )
        self.data_mass_window.data_added.connect(self._reload_consumables_data)
        self.data_mass_window.show()

    def open_emission_factor_window(self):
        """Ouvre la fenêtre dédiée aux facteurs d'émission matériaux/liquides."""
        if self._raise_existing_data_mass_window():
            return
        self.data_mass_window = DataMassWindow(
            parent=self,
            data_materials=self.data_materials,
            base_path=self.data_manager.base_path,
            user_path=self.data_manager.user_path,
            mode_filter="factor",
            initial_mode=DataMassWindow.MODE_SOLID_FACTOR,
            sqlite_path=getattr(self.data_manager, "sqlite_path", None),
        )
        self.data_mass_window.data_added.connect(self._reload_consumables_data)
        self.data_mass_window.show()

    def _reload_consumables_data(self):
        """Recharge les DataFrames de consommables dans le DataManager après un ajout."""
        try:
            self.data_manager.reload()
            self.data_masse = self.data_manager.get_data_masse()
            self.data_liquides = self.data_manager.get_data_liquides()
            self.data_materials = self.data_manager.get_data_materials()
            self._rebuild_search_indexes()
            if self.category_combo is not None:
                self.update_subsubcategory_names()
                self.update_nacres_visibility()
        except Exception as e:
            QMessageBox.warning(self, "Rechargement données",
                                f"Impossible de recharger les consommables : {e}")
    
    def define_user_manip_from_history(self):
        # 1) Préparer les lignes d'historique à afficher dans la fenêtre de création
        selected_rows = {idx.row() for idx in self.history_list.selectionModel().selectedRows()}
        history_items = []
        for row in range(self.history_list.rowCount()):
            cell0 = self.history_list.item(row, 0)
            data = cell0.data(Qt.UserRole) if cell0 else None
            if not data:
                continue
            cols = [
                self.history_list.item(row, c).text()
                if self.history_list.item(row, c) else ""
                for c in range(5)
            ]
            history_items.append({
                "text": " | ".join(cols),
                "data": data,
                "selected": row in selected_rows,
            })

        if not history_items:
            QMessageBox.warning(
                self,
                "Historique vide",
                "Ajoutez au moins un calcul dans l'historique avant de définir une manip type."
            )
            return

        # 2) Afficher le dialogue pour sélectionner les lignes et saisir le nom
        dialog = UserManipDialog(self, history_items=history_items)
        if dialog.exec() == QDialog.Accepted:
            manip_name = dialog.get_manip_name()
            selected_history_data = dialog.get_selected_history_data()

            # 3) Construire la liste des items à partir de la sélection du dialogue
            items_list = []
            for data in selected_history_data:
                items_list.append({
                    "category": data.get("category", ""),
                    "subcategory": data.get("subcategory", ""),
                    "subsubcategory": data.get("subsubcategory", ""),
                    "code_nacres": data.get("code_nacres", ""),
                    "year": data.get("year", 0),
                    "days": data.get("days", 0),
                    "name": data.get("name", ""),
                    "value": data.get("value", 0.0),
                    "unit": data.get("unit", ""),
                    "quantity": data.get("quantity", 0.0),
                    "consommable": data.get("consommable", ""),
                    "conditionnement": data.get("conditionnement", ""),
                    "origine": data.get("origine", self.data_manager.TRANSPORT_DEFAULT),
                    "electricity_type": data.get("electricity_type", ""),
                })
            if not items_list:
                QMessageBox.warning(
                    self, 
                    "Aucun item valide", 
                    "Les éléments sélectionnés sont vides ou invalides."
                )
                return

            # 4) Ajouter la manip en base (source = "utilisateur·rice")
            try:
                source_label = ManipsTypeDB.SOURCE_USER
                self.manips_db.add_manip(manip_name, items_list, source=source_label)
                QMessageBox.information(
                    self, 
                    "Manip ajoutée", 
                    f"La manip «{manip_name}» a bien été ajoutée dans la base (source={source_label})."
                )
                self.refresh_manip_type_combo()
            except Exception as e:
                QMessageBox.warning(self, "Erreur", f"Impossible d'ajouter la manip : {e}")

    def refresh_manip_type_combo(self):
        # On vide la combo
        self.manip_type_combo.clear()
        self.manip_type_combo.addItem("Sélectionnez une manip...")

        # On récupère la liste complète (avec id, name, source)
        manip_list = self.manips_db.list_manips_with_id()

        # On boucle sur chaque manip
        for m in manip_list:
            # Le texte qu'on veut afficher
            display_text = f"{m['name']} - {m['source']}"
            manip_data = {"name": m["name"], "source": m["source"]}
            
            # On ajoute l'item dans la combo
            # - `display_text` est ce que l'utilisateur voit,
            # - `name` et `source` sont stockés dans l'UserRole pour un usage ultérieur
            self.manip_type_combo.addItem(display_text, userData=manip_data)
        self.update_delete_manip_button()
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
        subcategory = self._current_subcategory()
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
        selected_consumable = (
            self._selected_consumable_data()
            if self.conso_filtered_combo.isVisible() else None
        )
        if selected_consumable:
            code_nacres = selected_consumable["code_nacres"] or code_nacres
            consommable = selected_consumable["consommable"] or "NA"
        conditionnement = selected_consumable.get("conditionnement", "") if selected_consumable else ""
            
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
        days = 1
        if self.days_field.isEnabled() and self.days_field.text().strip():
            try:
                days = int(self.days_field.text().strip())
            except ValueError:
                QMessageBox.warning(self, 'Erreur', "Le nombre de jours doit être un entier valide.")
                return

        # !! IMPORTANT !!
        # On NE MULTIPLIE PAS PAR `days` ICI si c'est un Véhicule.
        # On envoie 'val' = "km/jour" et 'days' séparément, 
        # afin que carbon_calculator fasse total_value = val * days.
        #
        # Pour Achats (ou autres), c'est pareil : on envoie juste la valeur (ex. euros tot ou /jour).
        # => carbon_calculator décidera s'il multiplie ou non.

        # Calcul massique => quantity
        quantity = 0.0
        if self.quantity_label.isVisible() and self.quantity_input.isVisible():
            try:
                quantity_str = self.quantity_input.text().strip().replace(',', '.')
                quantity_raw = float(quantity_str) if quantity_str else 0.0
            except ValueError:
                quantity_raw = 0.0
            # Solide en vrac : convertir grammes → unités fractionnaires pour le calculateur
            if self._current_masse_unitaire_g and self._current_masse_unitaire_g > 0:
                quantity = quantity_raw / self._current_masse_unitaire_g
            else:
                quantity = quantity_raw

        custom_fe = 0.0
        if self.fe_massique_input is not None and self.fe_massique_input.isVisible():
            custom_fe = safe_float(self.fe_massique_input.text().strip().replace(',', '.'))

        data_dict = {
            'category': category,
            'subcategory': subcategory,
            'subsubcategory': subsubcategory,
            'name': category_nacres,
            'year': year,
            'value': val,   # c'est km/jour pour Véhicules, euros pour Achats, etc.
            'days': days,
            'code_nacres': code_nacres,
            'consommable': consommable,
            'conditionnement': conditionnement,
            'quantity': quantity,
            'origine': self.origine_combo.currentText() if self.origine_combo and self.origine_combo.isVisible() else self.data_manager.TRANSPORT_DEFAULT,
            'custom_fe': custom_fe,
        }

        if category == 'Achats' and consommable and consommable != 'NA':
            row = self._find_consumable_mass_row(code_nacres, consommable, conditionnement)
            if row is not None:
                data_dict['masse_unitaire'] = safe_float(
                    row.get(self.data_manager.MASSE_G_COL, 0.0)
                )

        ep, ep_err, em, em_err, tm, msg = self.carbon_calculator.compute_emission_data(data_dict)
        if msg:
            if msg.startswith("WARN:"):
                QMessageBox.warning(self, "Matériaux non trouvés", msg[5:])
            else:
                self._result_show_error(msg)
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
            'conditionnement': conditionnement,
            'unit': self.current_unit,
            'quantity': quantity,
            'origine': data_dict['origine'],
        }

        self.create_or_update_history_item(new_data)
        self.update_total_emissions()
        self.input_field.clear()
        if self.quantity_input is not None:
            self.quantity_input.clear()
        if self.fe_massique_input is not None:
            self.fe_massique_input.clear()
        self.data_changed.emit()

    def modify_selected_calculation(self):
        """
        Modifie un calcul sélectionné dans l'historique.

        Ouvre une boîte de dialogue pour permettre à l'utilisateur de modifier les données d'un calcul existant.
        Si la modification est acceptée, recalcule les émissions et met à jour l'historique ainsi que les totaux.
        """
        current_row = self.history_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, 'Erreur', 'Veuillez sélectionner un calcul à modifier.')
            return

        cell0 = self.history_list.item(current_row, 0)
        old_data = cell0.data(Qt.UserRole) if cell0 else None
        if not old_data:
            QMessageBox.warning(self, 'Erreur', 'Aucune donnée disponible pour cet élément.')
            return

        dialog = EditCalculationDialog(self, data=old_data,
                                    main_data=self.data,
                                    data_masse=self.data_masse,
                                    data_materials=self.data_materials,
                                    data_liquides=self.data_liquides,
                                    data_manager=self.data_manager)
        if dialog.exec() == QDialog.Accepted:
            modified_data = dialog.modified_data
            # On suppose que modified_data['value'] = val/jour
            # et modified_data['days'] = days.
            ep, ep_err, em, em_err, tm, msg_price = self.carbon_calculator.compute_emission_data(modified_data)
            if msg_price:
                self._result_show_error(msg_price)
                return

            # Préserver les champs non édités dans le dialog (ex. origine)
            if 'origine' not in modified_data:
                modified_data['origine'] = old_data.get('origine', self.data_manager.TRANSPORT_DEFAULT)

            # On met à jour les champs calculés
            modified_data['emissions_price'] = ep
            modified_data['emissions_price_error'] = ep_err
            modified_data['emission_mass'] = em
            modified_data['emission_mass_error'] = em_err
            modified_data['total_mass'] = tm

            self.history_list.removeRow(current_row)
            self.create_or_update_history_item(modified_data, insert_at=current_row)
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
        total_all_price = 0.0
        total_all_price_err_sq = 0.0

        total_mass_price = 0.0
        total_mass_price_err_sq = 0.0

        total_mass = 0.0
        total_mass_err_sq = 0.0

        for i in range(self.history_list.rowCount()):
            item = self.history_list.item(i, 0)
            data = item.data(Qt.UserRole) if item else None
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

        def _fmt(label, val, err):
            return (
                f"<b>{label} :</b> {val:.4f} "
                f"<span style='color:#6b9e7a; font-size:11px'>± {err:.4f}</span> kg CO₂e"
            )

        self._result_show_ok("<br>".join([
            _fmt("Toutes catégories (méthode prix)", total_all_price, all_price_err),
            _fmt("Consommables (méthode prix)", total_mass_price, mass_price_err),
            _fmt("Consommables (méthode masse)", total_mass, mass_err),
        ]))

    def _find_consumable_mass_row(self, code_nacres, consommable, packaging=""):
        if self.data_masse is None or self.data_masse.empty:
            return None
        mask = (
            self._nacres_code_mask(self.data_masse[self.data_manager.CODE_NACRES_COL], code_nacres) &
            (self.data_masse[self.data_manager.CONSOMMABLE_COL].astype(str).str.strip() == clean_text(consommable))
        )
        rows = self.data_masse[mask]
        pack = clean_text(packaging)
        condt_col = getattr(self.data_manager, "CONDT_IJM_COL", "condt_ijm")
        if pack and condt_col in rows.columns:
            exact_pack = rows[rows[condt_col].fillna("").astype(str).str.strip() == pack]
            if not exact_pack.empty:
                rows = exact_pack
        return rows.iloc[0] if not rows.empty else None

    def _find_liquid_row(self, code_nacres, consommable, packaging=""):
        if self.data_liquides is None or self.data_liquides.empty:
            return None
        mask = self._nacres_code_mask(self.data_liquides[self.data_manager.CODE_NACRES_COL], code_nacres)
        product_col = self.data_liquides.get("Produit")
        if product_col is not None and clean_text(consommable):
            mask &= product_col.astype(str).str.strip() == clean_text(consommable)
        rows = self.data_liquides[mask]
        pack = clean_text(packaging)
        condt_col = getattr(self.data_manager, "CONDT_IJM_COL", "condt_ijm")
        if pack and condt_col in rows.columns:
            exact_pack = rows[rows[condt_col].fillna("").astype(str).str.strip() == pack]
            if not exact_pack.empty:
                rows = exact_pack
        return rows.iloc[0] if not rows.empty else None

    def _mass_detail_lines(self, data):
        code_nacres = clean_text(data.get("code_nacres"))
        consommable = clean_text(data.get("consommable"))
        conditionnement = clean_text(data.get("conditionnement"))
        quantity = safe_float(data.get("quantity"), default=0.0)
        if not code_nacres or code_nacres == "NA" or not consommable or consommable == "NA" or quantity <= 0:
            return []

        solid_row = self._find_consumable_mass_row(code_nacres, consommable, conditionnement)
        if solid_row is not None:
            factor_row = self._solid_row_liquid_factor(solid_row)
            if factor_row is not None:
                unit = clean_text(solid_row.get(getattr(self.data_manager, "UNITE_LIQUIDE_COL", "Unité liquide"), "")) or "mL"
                dens = safe_float(factor_row.get("Densité (g/mL)"), default=0.0)
                mass_kg = dens * quantity / 1000.0 if clean_text(unit).casefold() == "ml" else 0.0
                lines = [
                    "Détail masse liquide :",
                    f"- Quantité : {format_quantity(quantity)} {unit}",
                    f"- Facteur source : {clean_text(factor_row.get('Produit', ''))}",
                ]
                if dens > 0:
                    lines.append(f"- Densité : {dens:.4f} g/mL")
                lines.append(f"Masse totale : {mass_kg:.4f} kg")
                return lines
            specs = [
                ("Consommable", self.data_manager.MASSE_G_COL, self.data_manager.MATERIAU_COL, False),
                ("Consommable 2", getattr(self.data_manager, "MASSE_G2_COL", ""), getattr(self.data_manager, "MATERIAU2_COL", ""), False),
                ("Consommable 3", getattr(self.data_manager, "MASSE_G3_COL", ""), getattr(self.data_manager, "MATERIAU3_COL", ""), False),
                ("Emballage secondaire", self.data_manager.MASSE_EMBALLAGE_COL, self.data_manager.MATERIAU_EMBALLAGE_COL, False),
                ("Conditionnement primaire", self.data_manager.MASSE_CONDITIONNEMENT_COL, self.data_manager.MATERIAU_CONDITIONNEMENT_COL, True),
            ]
            lines = ["Détail masse :"]
            total_physical_kg = 0.0
            for label, mass_col, material_col, divide_by_pack in specs:
                if not mass_col or mass_col not in solid_row.index:
                    continue
                mass_g = safe_float(solid_row.get(mass_col), default=0.0)
                if divide_by_pack:
                    pack_count = safe_float(solid_row.get(self.data_manager.NOMBRE_PAR_COND_COL), default=1.0)
                    if pack_count <= 0:
                        continue
                    mass_g = mass_g / pack_count
                material = clean_text(solid_row.get(material_col, "")) if material_col in solid_row.index else ""
                if mass_g <= 0 and not material:
                    continue
                total_kg = quantity * mass_g / 1000.0
                total_physical_kg += total_kg
                material_text = f" ({material})" if material else ""
                lines.append(
                    f"- {label} : {mass_g:.4f} g x {format_quantity(quantity)} = {total_kg:.4f} kg{material_text}"
                )
            if total_physical_kg > 0:
                lines.append(f"Masse physique totale : {total_physical_kg:.4f} kg")
            total_mass = safe_float(data.get("total_mass"), default=0.0)
            if total_mass > 0 and abs(total_mass - total_physical_kg) > 1e-9:
                lines.append(f"Masse comptabilisée eCO₂ : {total_mass:.4f} kg")
            return lines

        liquid_row = self._find_liquid_row(code_nacres, consommable, conditionnement)
        if liquid_row is not None:
            unit = clean_text(liquid_row.get("Unité", "")) or "mL"
            unit_clean = unit.casefold()
            dens = safe_float(liquid_row.get("Densité (g/mL)"), default=0.0)
            if unit_clean in {"kg", "kilogramme", "kilogrammes"}:
                mass_kg = quantity
                detail = f"- Quantité : {format_quantity(quantity)} {unit}"
            elif unit_clean in {"g", "gramme", "grammes"}:
                mass_kg = quantity / 1000.0
                detail = f"- Quantité : {format_quantity(quantity)} {unit}"
            else:
                mass_kg = dens * quantity / 1000.0
                detail = f"- Volume : {format_quantity(quantity)} {unit}"
            lines = ["Détail masse liquide :", detail]
            if dens > 0 and unit_clean not in {"g", "kg", "gramme", "grammes", "kilogramme", "kilogrammes"}:
                lines.append(f"- Densité : {dens:.4f} g/mL")
            lines.append(f"Masse totale : {mass_kg:.4f} kg")
            return lines

        total_mass = safe_float(data.get("total_mass"), default=0.0)
        if total_mass > 0:
            return ["Détail masse :", f"Masse totale : {total_mass:.4f} kg"]
        return []

    def _history_tooltip(self, data):
        lines = []
        subcategory = clean_text(data.get("subcategory"))
        display_subcategory, subcategory_tip = format_subcategory_label(subcategory)
        if subcategory_tip:
            lines.append(f"{display_subcategory} : {subcategory_tip}")

        code_nacres = clean_text(data.get("code_nacres"))
        consommable = clean_text(data.get("consommable"))
        conditionnement = clean_text(data.get("conditionnement"))
        if code_nacres and code_nacres != "NA":
            lines.append(f"Code NACRES : {code_nacres}")
        if consommable and consommable != "NA":
            lines.append(f"Consommable : {consommable}")
            if conditionnement:
                lines.append(f"Conditionnement : {conditionnement}")
            lines.append(f"Quantité : {format_quantity(data.get('quantity'))}")
            unit = display_unit(data.get("unit")) or "€"
            lines.append(f"Valeur : {safe_float(data.get('value')):.2f} {unit}")

        mass_lines = self._mass_detail_lines(data)
        if mass_lines:
            if lines:
                lines.append("")
            lines.extend(mass_lines)
        return "\n".join(lines)

    def create_or_update_history_item(self, data, item=None, insert_at=None):
        category    = data.get('category', '')
        subcategory = data.get('subcategory', '')
        name        = data.get('name', '')
        value       = data.get('value', 0.0)
        unit        = data.get('unit', '')
        ep          = data.get('emissions_price', 0.0)
        ep_err      = data.get('emissions_price_error', 0.0)
        em          = data.get('emission_mass', 0.0)
        em_err      = data.get('emission_mass_error', 0.0)
        tm          = data.get('total_mass', 0.0)
        code_nacres = data.get('code_nacres', 'NA')
        consommable = data.get('consommable', 'NA')
        conditionnement = clean_text(data.get('conditionnement', ''))
        quantity    = data.get('quantity', 0.0)
        subcategory_display, _ = format_subcategory_label(subcategory)
        is_consumable_item = (
            category == "Achats"
            and clean_text(consommable)
            and clean_text(consommable) != "NA"
        )

        def fmt(val, err):
            if err and err > 0:
                return f"{val:.4f} ± {err:.4f}"
            return f"{val:.4f}"

        _SENTINEL = {'NA', 'nan', 'none', 'None', ''}

        def _valid(val):
            return bool(val) and str(val) not in _SENTINEL

        # ── Colonne "Élément" ────────────────────────────────────────────
        if category == 'Machine':
            elec = data.get('electricity_type', '')
            element = f"{subcategory} : {elec}" if elec and str(elec) not in _SENTINEL else subcategory
        elif category == 'Véhicules':
            parts = [p for p in (subcategory, code_nacres, name) if _valid(p)]
            element = " : ".join(parts)
        elif is_consumable_item:
            suffix = f" - {conditionnement}" if conditionnement else ""
            element = f"{subcategory_display} : {consommable}{suffix}"
        else:
            parts = [p for p in (subcategory_display[:20], code_nacres, name) if _valid(p)]
            element = " : ".join(parts)
            if _valid(consommable):
                element += f" ({consommable})"

        # ── Colonne "Valeur" ─────────────────────────────────────────────
        if category == 'Machine':
            valeur = f"{float(value):.2f} kWh"
        elif category == 'Véhicules':
            days = data.get('days', 1)
            try:
                total_km = float(value) * int(days)
                valeur = f"{float(value):.2f} km/j × {days} j = {total_km:.0f} km"
            except (ValueError, TypeError):
                valeur = f"{value} {unit}"
        elif is_consumable_item:
            unit_display = display_unit(unit) or "€"
            valeur = f"Quantité : {format_quantity(quantity)} | Valeur : {safe_float(value):.2f} {unit_display}"
        else:
            valeur = f"{value} {unit}"

        # ── Colonnes eCO₂ ────────────────────────────────────────────────
        eco2_prix  = fmt(ep, ep_err)
        eco2_masse = fmt(em, em_err) if em and em != 0.0 else ""

        # ── Insérer la ligne ─────────────────────────────────────────────
        row = insert_at if insert_at is not None else self.history_list.rowCount()
        self.history_list.insertRow(row)

        tooltip = self._history_tooltip(data)

        cell0 = QTableWidgetItem(category)
        cell0.setData(Qt.UserRole, data)
        element_item = QTableWidgetItem(element)
        value_item = QTableWidgetItem(valeur)
        price_item = QTableWidgetItem(eco2_prix)
        mass_item = QTableWidgetItem(eco2_masse)
        if tooltip:
            for table_item in (cell0, element_item, value_item, mass_item):
                table_item.setToolTip(tooltip)

        self.history_list.setItem(row, 0, cell0)
        self.history_list.setItem(row, 1, element_item)
        self.history_list.setItem(row, 2, value_item)
        self.history_list.setItem(row, 3, price_item)
        self.history_list.setItem(row, 4, mass_item)

        return row

    def delete_selected_calculation(self):
        """
        Supprime le calcul actuellement sélectionné dans l'historique.

        Retire l'élément sélectionné de la liste historique et met à jour le total des émissions.
        """
        selected_rows = sorted(
            {idx.row() for idx in self.history_list.selectionModel().selectedRows()},
            reverse=True
        )
        if not selected_rows:
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un ou plusieurs calculs à supprimer.")
            return

        count = len(selected_rows)
        message = (
            "Supprimer le calcul sélectionné ?"
            if count == 1
            else f"Supprimer les {count} calculs sélectionnés ?"
        )
        reply = QMessageBox.question(
            self,
            "Confirmer la suppression",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for row in selected_rows:
            self.history_list.removeRow(row)

        self.update_total_emissions()
        self._update_history_buttons_state()
        self.data_changed.emit()

    def export_data(self):
        """
        Exporte les données de l'historique des calculs vers un fichier.

        Ouvre une boîte de dialogue pour permettre à l'utilisateur de choisir le format de fichier,
        puis enregistre les données de l'historique dans le fichier sélectionné. Affiche un message de confirmation ou d'erreur.
        """
        from PySide6.QtWidgets import QFileDialog
        import pandas as pd
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer l'historique", "historique_labeco2.json",
            "Fichier JSON (*.json);;Fichier CSV (*.csv);;Fichier Excel (*.xlsx);;Tous les fichiers (*)"
        )
        if not file_name:
            return

        rows = []
        for i in range(self.history_list.rowCount()):
            cell0 = self.history_list.item(i, 0)
            d = cell0.data(Qt.UserRole) if cell0 else None
            if d:
                rows.append(d)

        if not rows:
            QMessageBox.information(self, "Export", "Aucun élément dans l'historique.")
            return

        df = pd.DataFrame(rows)
        _, ext = os.path.splitext(file_name)
        ext = ext.lower()
        if not ext:
            file_name += ".json"
            ext = ".json"

        try:
            if ext == '.json':
                payload = {
                    "format": "LABeCO2 history",
                    "version": 1,
                    "items": rows,
                }
                with open(file_name, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
            elif ext == '.csv':
                df.to_csv(file_name, index=False, sep=';')
            elif ext == '.xlsx':
                df.to_excel(file_name, index=False)
            else:
                file_name += ".json"
                with open(file_name, "w", encoding="utf-8") as f:
                    json.dump({"format": "LABeCO2 history", "version": 1, "items": rows}, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Export", f"Exporté avec succès dans {file_name}")
        except Exception as e:
            QMessageBox.warning(self, "Erreur Export", f"{e}")

    def import_data(self):
        """
        Importe des données dans l'historique des calculs à partir d'un fichier.

        Ouvre une boîte de dialogue pour permettre à l'utilisateur de sélectionner un fichier,
        lit les données du fichier, convertit les colonnes attendues, et ajoute les éléments à l'historique.
        Affiche un message de confirmation ou d'erreur.
        """
        from PySide6.QtWidgets import QFileDialog
        import pandas as pd
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Importer l'historique", "",
            "Tous les fichiers (*);;Fichier JSON (*.json);;Fichier CSV (*.csv);;Fichier Excel (*.xlsx)"
        )
        if not file_name:
            return

        _, ext = os.path.splitext(file_name)
        ext = ext.lower()
        try:
            if ext == '.json':
                with open(file_name, encoding="utf-8") as f:
                    payload = json.load(f)
                rows = payload.get("items", payload) if isinstance(payload, dict) else payload
                if not isinstance(rows, list):
                    raise ValueError("Le JSON ne contient pas de liste d'éléments.")
                df = pd.DataFrame(rows)
            elif ext == '.csv':
                # keep_default_na=False : empêche pandas de convertir 'NA' en NaN
                # (sinon astype(str) produit la chaîne 'nan')
                df = pd.read_csv(file_name, sep=';', keep_default_na=False)
            elif ext == '.xlsx':
                df = pd.read_excel(file_name)
            else:
                df = pd.read_csv(file_name, sep=';', keep_default_na=False)
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
        # Normaliser les résidus 'nan' (exports antérieurs où un NaN pandas a été sérialisé)
        for col in ["code_nacres", "consommable"]:
            if col in df.columns:
                df[col] = df[col].replace({'nan': 'NA', 'none': 'NA', 'None': 'NA', '': 'NA'})
        for col in ["name", "subsubcategory"]:
            if col in df.columns:
                df[col] = df[col].replace({'nan': '', 'none': '', 'None': ''})

        # Pour les Achats : si code_nacres est absent/NA/nan mais subsubcategory est renseigné,
        # utiliser les 4 premiers caractères de subsubcategory comme code NACRES.
        if all(c in df.columns for c in ('category', 'code_nacres', 'subsubcategory')):
            missing_code = (
                (df['category'] == 'Achats') &
                (df['code_nacres'].str.upper().isin(['NA', 'NAN', ''])) &
                (~df['subsubcategory'].str.upper().isin(['', 'NAN', 'NA']))
            )
            df.loc[missing_code, 'code_nacres'] = df.loc[missing_code, 'subsubcategory'].str[:4]

        count_imported = 0
        for _, row in df.iterrows():
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
                'days': days,
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
                            - 'coverage' : Couverture méthodologique globale.
                            - 'coverage_category' : Couverture méthodologique par catégorie.
        """
        # Détermine le nom de l'attribut correspondant à la fenêtre graphique.
        # Exemple : pour 'pie', on recherche 'pie_chart_window'.
        window_attr = f"{chart_type}_chart_window"

        # Récupère la fenêtre existante pour ce type de graphique (si elle existe déjà).
        window = getattr(self, window_attr, None)
        if window is not None and not isValid(window):
            setattr(self, window_attr, None)
            window = None

        if window is None:  # Si la fenêtre n'existe pas encore :
            # Dictionnaire associant chaque type de graphique à sa classe correspondante.
            window_class = {
                'pie': PieChartWindow,
                'bar': BarChartWindow,
                'proportional_bar': ProportionalBarChartWindow,
                'stacked_bar_consumables': StackedBarConsumablesWindow,
                'nacres_bar': NacresBarChartWindow,
                'proportional_bar_mass': ProportionalBarChartNacresWindow,
                'pareto': ParetoChartWindow,
                'transport': TransportChartWindow,
                'transport_consumable': TransportConsumableChartWindow,
                'transport_factor': TransportFactorChartWindow,
                'transport_scenario': TransportScenarioChartWindow,
                'transport_top': TransportTopChartWindow,
                'coverage': CoverageWindow,
                'coverage_category': CoverageCategoryWindow
            }.get(chart_type)

            # Vérifie si le type demandé est valide (i.e., présent dans le dictionnaire).
            if window_class is None:
                # Affiche un avertissement si le type de graphique est inconnu.
                QMessageBox.warning(self, "Erreur", f"Type de graphique inconnu : {chart_type}")
                return  # Sort de la fonction sans rien faire.

            # Crée une nouvelle instance de la fenêtre pour le type de graphique spécifié.
            window = window_class(self)

            # finished(int) transmet un code de fermeture : il ne doit pas remplacer window_attr.
            def _on_finished(_result=None, attr=window_attr, w=window):
                if getattr(self, attr, None) is w:
                    setattr(self, attr, None)

            window.finished.connect(_on_finished)

            # Stocke la fenêtre créée dans l'attribut correspondant à son type.
            setattr(self, window_attr, window)
        else:
            # Si la fenêtre existe déjà, met à jour ses données.
            window.refresh_data()

        # Affiche la fenêtre graphique.
        window.show()
        window.raise_()  # Amène la fenêtre au premier plan.
        window.activateWindow()  # Active la fenêtre pour qu'elle soit prête à recevoir des interactions.

    def generate_pdf_summary(self):
        """Génère un PDF complet : page de résumé, tableau historique, puis tous les graphiques."""
        import datetime
        from matplotlib.backends.backend_pdf import PdfPages
        from matplotlib.figure import Figure
        from PySide6.QtWidgets import QFileDialog, QProgressDialog
        from PySide6.QtCore import Qt

        file_name, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le résumé PDF", "bilan_carbone.pdf",
            "Fichiers PDF (*.pdf)"
        )
        if not file_name:
            return
        if not file_name.lower().endswith('.pdf'):
            file_name += '.pdf'

        progress = QProgressDialog("Génération du PDF…", None, 0, 0, self)
        progress.setWindowTitle("Résumé PDF")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        QApplication.processEvents()

        try:
            with PdfPages(file_name) as pdf:

                # ── Page 1 : résumé texte ─────────────────────────────────
                fig = Figure(figsize=(8.27, 11.69))
                ax = fig.add_axes([0.1, 0.1, 0.8, 0.8])
                ax.axis('off')

                now = datetime.datetime.now().strftime("%d/%m/%Y")
                result_text = self.result_area.text() if self.result_area else ""
                # nettoyer les balises HTML basiques pour le PDF
                import re
                html_lines = re.split(r'<br\s*/?>', result_text, flags=re.IGNORECASE)
                clean_lines = [
                    re.sub(r'<[^>]+>', '', l).replace('&nbsp;', ' ').strip()
                    for l in html_lines
                ]
                clean = '\n'.join(l for l in clean_lines if l)

                ax.text(0.5, 0.95, "Bilan Carbone LABeCO₂",
                        ha='center', va='top', fontsize=20, fontweight='bold',
                        transform=ax.transAxes)
                ax.text(0.5, 0.88, f"Généré le {now}",
                        ha='center', va='top', fontsize=11, color='#555555',
                        transform=ax.transAxes)
                ax.plot([0.1, 0.9], [0.84, 0.84], color='#cccccc', linewidth=0.8,
                        transform=ax.transAxes)
                ax.text(0.5, 0.80, clean,
                        ha='center', va='top', fontsize=12,
                        transform=ax.transAxes, linespacing=2.0)
                pdf.savefig(fig, bbox_inches='tight')

                # ── Page 2 : tableau historique ───────────────────────────
                def _pdf_str(val):
                    s = str(val or '').strip()
                    return '' if s.lower() in ('nan', 'none', 'na') else s

                rows = []
                for data in iter_history_data(self.history_list):
                    cat  = _pdf_str(data.get('category', ''))
                    name = _pdf_str(data.get('name', ''))
                    sub  = _pdf_str(data.get('subcategory', ''))
                    elem = name or sub or cat
                    ep   = float(data.get('emissions_price', 0) or 0)
                    em   = float(data.get('emission_mass', 0) or 0)
                    rows.append([cat, elem[:40], f"{ep:.3f}", f"{em:.3f}"])

                if rows:
                    fig2 = Figure(figsize=(11.69, 8.27))
                    ax2 = fig2.add_axes([0.03, 0.1, 0.94, 0.82])
                    ax2.axis('off')
                    ax2.set_title("Historique des calculs", fontsize=14,
                                  fontweight='bold', pad=12)
                    col_labels = ["Catégorie", "Élément", "eCO₂ prix (kg)", "eCO₂ masse (kg)"]
                    col_widths = [0.14, 0.52, 0.17, 0.17]
                    tbl = ax2.table(
                        cellText=rows,
                        colLabels=col_labels,
                        colWidths=col_widths,
                        loc='center',
                        cellLoc='left',
                    )
                    tbl.auto_set_font_size(False)
                    tbl.set_fontsize(8)
                    tbl.scale(1, 1.4)
                    for (r, c), cell in tbl.get_celld().items():
                        if r == 0:
                            cell.set_facecolor('#1d4ed8')
                            cell.set_text_props(color='white', fontweight='bold')
                        elif r % 2 == 0:
                            cell.set_facecolor('#f0f7ff')
                        cell.set_edgecolor('#dddddd')
                    pdf.savefig(fig2, bbox_inches='tight')

                # ── Pages graphiques ──────────────────────────────────────
                chart_classes = [
                    ('pie',                 PieChartWindow),
                    ('proportional_bar',    ProportionalBarChartWindow),
                    ('bar',                 BarChartWindow),
                    ('pareto',              ParetoChartWindow),
                    ('nacres_bar',          NacresBarChartWindow),
                    ('proportional_bar_mass', ProportionalBarChartNacresWindow),
                    ('transport',           TransportChartWindow),
                    ('transport_consumable', TransportConsumableChartWindow),
                    ('transport_factor',    TransportFactorChartWindow),
                    ('transport_top',       TransportTopChartWindow),
                    ('coverage',            CoverageWindow),
                    ('coverage_category',   CoverageCategoryWindow),
                ]
                for _key, cls in chart_classes:
                    try:
                        win = cls(self)
                        QApplication.processEvents()
                        if hasattr(win, 'figure') and win.figure is not None:
                            pdf.savefig(win.figure, bbox_inches='tight')
                        win.close()
                        win.deleteLater()
                        QApplication.processEvents()
                    except Exception:
                        pass

        except Exception as e:
            QMessageBox.warning(self, "Erreur PDF", f"Impossible de générer le PDF :\n{e}")
            return
        finally:
            progress.close()

        QMessageBox.information(self, "PDF généré",
                                f"Résumé enregistré dans :\n{file_name}")

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

    def generate_pareto_chart(self):
        self.generate_chart('pareto')

    def generate_transport_chart(self):
        self.generate_chart('transport')

    def generate_transport_consumable_chart(self):
        self.generate_chart('transport_consumable')

    def generate_transport_factor_chart(self):
        self.generate_chart('transport_factor')

    def generate_transport_top_chart(self):
        self.generate_chart('transport_top')

    def generate_transport_scenario_chart(self):
        self.generate_chart('transport_scenario')

    def generate_coverage_chart(self):
        self.generate_chart('coverage')

    def generate_coverage_category_chart(self):
        self.generate_chart('coverage_category')

    def _on_footer_link(self, href):
        if href == "methodo":
            self.show_methodology_popup()
        else:
            self.show_sources_popup(href)

    def show_methodology_popup(self):
        """Affiche la fenêtre de documentation méthodologique."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea, QWidget

        dialog = QDialog(self)
        dialog.setWindowTitle("Méthodologie de calcul")
        dialog.setModal(True)
        dialog.resize(620, 520)

        outer = QVBoxLayout(dialog)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        inner = QVBoxLayout(container)

        text = QLabel()
        text.setTextFormat(Qt.RichText)
        text.setOpenExternalLinks(True)
        text.setWordWrap(True)
        text.setText("""
<p><b>Contexte et objectif</b></p>
<p>
LABeCO₂ calcule l'empreinte carbone d'activités de recherche à l'échelle individuelle ou d'un projet
expérimental, et non à l'échelle d'un laboratoire ou d'une institution.
L'objectif n'est pas de produire une valeur absolue parfaitement exacte, mais une estimation cohérente,
reproductible et comparable entre différentes manipulations, afin d'identifier les principaux postes
d'émission et de réfléchir à des leviers de réduction.
</p>
<p>
Le périmètre couvre les postes directement liés à la production scientifique : consommables, réactifs,
déplacements professionnels, machines et équipements électriques.
Les infrastructures mutualisées (bâtiments, climatisation, réseau informatique) et les coûts administratifs
sont exclus — ce choix est assumé et documenté.
</p>

<p><b>Méthode 1 : approche prix via les codes NACRES (modèle EEIO)</b></p>
<p>
Les facteurs d'émission par code NACRES (kg CO₂e/€) sont issus de la base
<a href="https://entrepot.recherche.data.gouv.fr/dataset.xhtml?persistentId=doi:10.57745/HZNS3S">PER1p5 (Labos 1point5)</a>.
Ils sont construits à partir de <b>modèles entrées-sorties étendus à l'environnement (EEIO)</b> :
toute l'économie est représentée comme un réseau d'échanges entre secteurs industriels, auquel on associe
les émissions réelles mesurées par euro produit.
</p>
<p>
Le modèle remonte toute la chaîne de façon matricielle : quand tu achètes 1 € de consommable plastique,
il calcule les émissions de la fabrication, du transport, de l'énergie, des services du distributeur,
de l'emballage. <b>Le transport n'est donc pas ajouté comme un pourcentage fixe</b> : il est capturé
indirectement via les achats intermédiaires du secteur. Cette approche systémique fonctionne bien à
l'échelle d'un laboratoire entier, mais introduit des erreurs plus importantes à l'échelle d'une seule
expérience, car le facteur NACRES est une <i>moyenne sectorielle</i> qui ne distingue pas un produit
fabriqué en Allemagne d'un produit fabriqué en Chine.
</p>
<p>Formule : <i>dépense (€) × facteur NACRES (kg CO₂e/€)</i></p>

<p><b>Méthode 2 : approche physique bottom-up par les matériaux</b></p>
<p>
Pour les consommables dont on connaît la masse et le matériau, une approche physique est utilisée en
complément. Les facteurs d'émission par matériau (kg CO₂e/kg) sont issus d'analyses de cycle de vie
rigoureuses (normes ISO 14040/14044), vérifiées par des tiers indépendants.
</p>
<p>
Ces facteurs couvrent l'extraction des matières premières et la fabrication jusqu'à la sortie d'usine
(<b>cradle-to-gate</b>). Exemple : le PMMA des cuvettes de spectrophotométrie est à
<b>3,75 kg CO₂e/kg</b> (PlasticsEurope EPD 2015, cradle-to-gate explicite).
</p>
<p>
Sources : <a href="https://base-empreinte.ademe.fr/">Base Empreinte® ADEME</a> (PP, PE, PS, PET, PVC,
PTFE, PC, papier, carton, verre) ;
<a href="https://www.petrochemistry.eu/wp-content/uploads/2018/01/PMMA-Eco-profile-EPD-1-15-1.pdf">PlasticsEurope EPD 2015</a>
(PMMA) ;
<a href="https://doi.org/10.1371/journal.pstr.0000080">Ragazzi 2023 (PLOS)</a>
(nitrile, solvants courants).
</p>
<p>Formule : <i>quantité × masse unitaire (kg) × facteur matériau (kg CO₂e/kg)</i>,
appliquée séparément au produit, à l'emballage secondaire et au conditionnement primaire.</p>

<p><b>Correction transport (méthode masse)</b></p>
<p>
Un facteur de transport s'ajoute à l'émission massique pour tenir compte du fret depuis
le fabricant jusqu'au laboratoire. L'utilisateur sélectionne la provenance du consommable ;
le facteur correspondant (kg CO₂e/kg de produit) est ajouté à l'émission calculée par la méthode masse.
</p>
<p>
Formule : <i>émission totale = émission matériaux + masse_kg × facteur_transport</i>.
L'incertitude du transport est propagée en quadrature avec celle des matériaux.
</p>
<p>
Si la provenance est inconnue, la valeur par défaut <b>"Inconnue (défaut)"</b> est utilisée :
<b>0,265 kg CO₂e/kg</b>, calculée comme la moyenne entre USA (0,18) et Asie (0,35) par fret maritime,
pour une distance évaluée à 14 000 km. Incertitude : ±30 %.
Ce choix assume que la majorité des consommables de laboratoire provient de zones lointaines
et transite par voie maritime (le fret express aérien est exclu du défaut).
</p>

<p><b>Véhicules et déplacements</b></p>
<p>
Formule : <i>km/jour × nombre de jours × facteur (kg CO₂e/km)</i>.
Facteurs issus de la base <a href="https://apps.labos1point5.org/documentation/carbon/ges-emissions-factors">GES 1point5</a>.
</p>

<p><b>Machines et équipements électriques</b></p>
<p>
La consommation correspond à la puissance de la machine (kW) multipliée par le temps d'utilisation (h).
Formule complète : <i>puissance (kW) × temps d'utilisation (h) × facteur électricité (kg CO₂e/kWh)</i>.<br>
Le facteur dépend du type d'électricité sélectionné (réseau France, mix européen, etc.)
et est issu de la base GES 1point5.
</p>

<p><b>Propagation des incertitudes</b></p>
<p>
Les incertitudes sont propagées en quadrature : racine de la somme des carrés des incertitudes absolues.
Cette approche suppose l'indépendance des sources d'incertitude.
Chaque facteur d'émission est associé à une incertitude relative (ex. : 0,10 = ±10 %).
</p>

<p><b>Affichage des résultats</b></p>
<p>Le récapitulatif distingue trois grandeurs :</p>
<ul>
  <li><b>Toutes catégories (méthode prix) :</b> total de l'historique, toutes activités, méthode prix.</li>
  <li><b>Consommables (méthode prix) :</b> sous-total des consommables ayant aussi un calcul massique,
  méthode prix — pour comparaison directe avec la ligne suivante.</li>
  <li><b>Consommables (méthode masse) :</b> mêmes consommables, méthode physique bottom-up.</li>
</ul>

<hr>

<p><b>Ce qui n'est pas encore intégré dans le calcul</b></p>

<p><i>1. Étape de moulage et injection plastique</i></p>
<p>
Les facteurs cradle-to-gate couvrent la résine plastique mais pas la mise en forme (moulage par injection,
thermoformage). Cette étape ajoute typiquement <b>+0,3 à +0,5 kg CO₂e/kg</b> selon le mix électrique
utilisé par le transformateur. Elle n'est pas encore intégrée dans la base de données matériaux.
</p>

<p><i>2. Empreinte carbone du numérique et de l'intelligence artificielle</i></p>
<p>
Internet, calculs distribués et modèles d'IA sont devenus omniprésents dans la recherche.
Cette dimension n'est pas encore intégrée dans LABeCO₂ et constitue un axe de développement futur.
</p>

<p><i>3. Biomolécules et protéines purifiées</i></p>
<p>
Les données disponibles sur l'empreinte carbone des protéines et réactifs biologiques purifiés
présentent des incertitudes extrêmement élevées (facteurs variant jusqu'à ×10 000 selon les sources).
Une base de données dédiée, construite collectivement avec les équipes spécialisées, est nécessaire
avant toute intégration fiable.
</p>
        """)
        inner.addWidget(text)
        container.setLayout(inner)
        scroll.setWidget(container)
        outer.addWidget(scroll)

        close_button = QPushButton("Fermer")
        close_button.clicked.connect(dialog.close)
        outer.addWidget(close_button)

        dialog.exec()

    def show_sources_popup(self, _link_str):
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
                <b><a href="https://apps.labos1point5.org/documentation/carbon/ges-emissions-factors">GES 1point5 - Facteurs d'émission</a></b><br>
                Données utilisées par l'application GES 1point5 pour l'électricité, les véhicules, les transports, etc.
            </li>
            <li>
                <b><a href="https://entrepot.recherche.data.gouv.fr/dataset.xhtml?persistentId=doi:10.57745/HZNS3S">Labos 1point5 (PER1p5) - Données achats</a></b><br>
                Données PER1p5 pour les achats (NACRES vers facteurs d'émission macro / méso / micro).<br>
                M. De Paepe, L. Jeanneau, J. Mariette, O. Aumont, A. Estevez-Torres, <i>Purchases dominate the carbon footprint of research laboratories</i>, bioRxiv 2023 (<a href="https://doi.org/10.1101/2023.04.04.535626">https://doi.org/10.1101/2023.04.04.535626</a>).
            </li>
            <li>
                <b><a href="https://www.amue.fr/publications/actualites/details/nomenclature-nacres-mise-a-jour-ce-mois-de-mars-2026">AMUE - Nomenclature NACRES mise à jour en mars 2026</a></b><br>
                Source de la nomenclature NACRES 2026 utilisée pour les nouveaux codes et leur statut de mise à jour.
            </li>
            <li>
                <b><a href="https://base-empreinte.ademe.fr/">Base Carbone®</a></b><br>
                Source officielle pour les données de l'ADEME (Agence de la Transition Écologique).
            </li>
            <li>
                <b><a href="https://labos1point5.org/">Labos 1point5</a></b><br>
                Plateforme collaborative pour la réduction de l'empreinte carbone dans les laboratoires de recherche.
            </li>
            <li>
                <b><a href="https://plasticseurope.org/fr/">PlasticsEurope</a></b><br>
                Organisation représentant les fabricants de plastiques en Europe, fournissant des données sur l'industrie.
            </li>
            <li>
                <b><a href="https://www.petrochemistry.eu/wp-content/uploads/2018/01/PMMA-Eco-profile-EPD-1-15-1.pdf">PlasticsEurope / Petrochemistry - PMMA Eco-profile EPD</a></b><br>
                Environmental Product Declaration du PMMA, janvier 2015. Valeur utilisée pour le PMMA : 3,75 kg CO₂e/kg pour la résine PMMA, périmètre cradle-to-gate.
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

        <p><b>Transport de marchandises :</b></p>
        <ul>
            <li>
                <b><a href="https://prod-basecarbonesolo.ademe-dri.fr/documentation/UPLOAD_DOC_FR/routier.htm">ADEME Base Carbone® — Transport routier marchandises</a></b><br>
                Facteurs d'émission pour le fret routier (camion), exprimés en kg CO₂e/t.km.
            </li>
            <li>
                <b><a href="https://prod-basecarbonesolo.ademe-dri.fr/documentation/UPLOAD_DOC_FR/ferroviaire.htm">ADEME Base Carbone® — Transport ferroviaire marchandises</a></b><br>
                Facteurs d'émission pour le fret ferroviaire, exprimés en kg CO₂e/t.km.
            </li>
            <li>
                <b><a href="https://prod-basecarbonesolo.ademe-dri.fr/documentation/UPLOAD_DOC_FR/aerien2.htm">ADEME Base Carbone® — Transport aérien</a></b><br>
                Facteurs d'émission pour le fret aérien cargo (1,9 kg CO₂e/t.km).
            </li>
            <li>
                <b><a href="https://bilans-ges.ademe.fr/ressources/etapes-dun-bilan-ges">ADEME — Étapes d'un bilan GES</a></b><br>
                Guide méthodologique ADEME pour la réalisation d'un bilan de gaz à effet de serre.
            </li>
            <li>
                <b><a href="https://www.carbone4.com/analyse-faq-fret">Carbone 4 — FAQ Fret</a></b><br>
                Analyse et questions fréquentes sur le calcul de l'empreinte carbone du fret.
            </li>
            <li>
                <b><a href="https://www.hellocarbo.com/blog/calculer/bilan-carbone-transport/">HelloCarbo — Bilan carbone transport</a></b><br>
                Synthèse des facteurs ADEME pour le transport de marchandises.
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
        <p><b> Crédits :</b></p>
        <ul>
            <li>
                <b><a href="https://www.ilfotografico.net/">Dario Danile</a></b>: Graphiste de l'icône de l'application.
            </li>
            <li>
                <b>Alexandre Souchaud</b> : Codeur de l'application.
            </li>
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

    def closeEvent(self, event):
        """Ferme proprement la connexion SQLite à la fermeture de la fenêtre."""
        self.manips_db.close()
        super().closeEvent(event)
