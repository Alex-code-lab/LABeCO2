# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# windows/data_mass_window.py
import os
import sys
import html
import re
from datetime import date
import pandas as pd
from PySide6.QtWidgets import (
    QMainWindow, QMessageBox, QVBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QWidget, QComboBox, QHBoxLayout, QLabel, QFileDialog, QToolTip,
    QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QDoubleValidator, QIntValidator

class DataMassWindow(QMainWindow):
    data_added = Signal()

    def __init__(self, parent=None, data_materials=None, base_path=None,
                 user_path=None, prefill_code=None, prefill_name=None,
                 prefill_source="solid"):
        super().__init__(parent)

        self.setWindowTitle("Gestion des consommables")
        self.setGeometry(100, 100, 860, 620)
        self.setMinimumSize(760, 520)

        # Résolution du base_path compatible PyInstaller
        if base_path is None:
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        # user_path : dossier persistant pour les HDF5 modifiables
        if user_path is None:
            user_path = base_path
        self._user_path = user_path

        self.nacres_hdf5_file = os.path.join(base_path, "data", "mass_factors", "nacres_2022.h5")
        self._all_nacres = []  # Will store (code, description)

        # HDF5 modifiable → user_path
        self.hdf5_file = os.path.join(user_path, "data", "mass_factors", "data_eCO2_masse_consommable.hdf5")

        self.columns = [
            "Consommable",
            "Marque",
            "Référence",
            "Code CAS",
            "Catégorie",
            "Code NACRES",
            "Masse unitaire (g)",
            "Matériau consommable",
            "Masse unitaire deuxieme materiaux (g)",
            "Matériau deuxieme materiaux",
            "Masse unitaire troisième materiaux (g)",
            "Matériau troisième materiaux",
            "Masse emballage unitaire (g)",
            "Matériau emballage",
            "Masse condionnement (g)",
            "Matériau conditionnement",
            "Nbr par conditionnement",
            "Prix du conditionnement",
            "date d'ajout",
            "Source/Signature",
            "Source catalogue IJM",
            "Lien / Note / Remarque",
            "condt_ijm",
            "designation_ijm",
            "code_ijm",
            "marque_ijm",
            "score_match",
        ]

        # Spécifique consommables liquides
        self.columns_liquids = [
            "Produit",
            "Type",
            "Code NACRES",
            "CAS",
            "Référence",
            "Unité",
            "Densité (g/mL)",
            "Concentration (mg/mL)",
            "Facteur CO₂ (kg CO₂e/kg)",
            "Incertitude (%)",
            "Volume flacon (mL)",
            "Matériau contenant",
            "Masse contenant (g)",
            "Matériau emballage",
            "Masse emballage (g)",
            "Source/Signature",
            "date d'ajout",
            "Note",
            "Prix du conditionnement",
            "Nbr par conditionnement",
            "Source catalogue IJM",
            "condt_ijm",
            "designation_ijm",
            "code_ijm",
            "marque_ijm",
            "score_match",
        ]

        # Fichier pour les consommables liquides (modifiable → user_path)
        self.hdf5_liquids = os.path.join(user_path, "data", "mass_factors", "data_eCO2_liquides_consommable.hdf5")

        # Charger ou initialiser les données
        self.data = self.charger_ou_initialiser_donnees()
        self.prefill_row_index = None

        # data_materials transmis par MainWindow
        # data_materials doit contenir 'Materiau' et 'eCO2_kg'
        self.data_materials = data_materials

        self.data_liquids = self.load_liquid_df()


        self.init_ui()
        self.afficher_donnees()

        if prefill_code or prefill_name:
            self.prefill_consumable(prefill_code or "", prefill_name or "", source=prefill_source)

    def charger_ou_initialiser_donnees(self):
        if os.path.exists(self.hdf5_file):
            try:
                df = pd.read_hdf(self.hdf5_file)
            except Exception as e:
                QMessageBox.warning(self, "Erreur", f"Impossible de charger le fichier HDF5 : {e}")
                df = pd.DataFrame(columns=self.columns)
        else:
            df = pd.DataFrame([{
                "Consommable": "Tube Falcon 15ml",
                "Marque": "N/A",
                "Référence": "N/A",
                "Code CAS": "",
                "Catégorie": "Consommable",
                "Code NACRES": "NB13",
                "Masse unitaire (g)": 6.7,
                "Matériau consommable": "Polypropylène (PP)",
                "Masse unitaire deuxieme materiaux (g)": "N/A",
                "Matériau deuxieme materiaux": "N/A",
                "Masse unitaire troisième materiaux (g)": "",
                "Matériau troisième materiaux": "",
                "Masse emballage unitaire (g)": "N/A",
                "Matériau emballage": "N/A",
                "Masse condionnement (g)": "N/A",
                "Matériau conditionnement": "N/A",
                "Nbr par conditionnement": "N/A",
                "Prix du conditionnement": "",
                "date d'ajout": "",
                "Source/Signature": "Alexandre Souchaud",
                "Source catalogue IJM": "",
                "Lien / Note / Remarque": "",
                "condt_ijm": "",
                "designation_ijm": "",
                "code_ijm": "",
                "marque_ijm": "",
                "score_match": "",
            }], columns=self.columns)
            self.sauvegarder_donnees(df)
        # --- Harmoniser les colonnes manquantes ---
        data = df
        for col in self.columns:
            if col not in data.columns:
                data[col] = ""
        return data

    def sauvegarder_donnees(self, df=None):
        if df is None:
            df = self.data

        directory = os.path.dirname(self.hdf5_file)
        if not os.path.exists(directory):
            os.makedirs(directory)

        try:
            df.to_hdf(self.hdf5_file, key='data', mode='w')
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Impossible de sauvegarder le fichier HDF5 : {e}")

    def add_section_header(self, title, mode=None):
        header = QLabel(title)
        header.setStyleSheet(
            "border-top: 1px solid #cbd5e1; "
            "color: #374151; font-weight: 700; "
            "padding-top: 8px; margin-top: 8px;"
        )
        self.form_layout.addRow(header)
        if mode == "solid":
            self.solid_section_headers.append(header)
        elif mode == "liquid":
            self.liquid_section_headers.append(header)
        return header

    def create_material_selector(self, combo):
        selector = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        info_button = QPushButton("i")
        info_button.setFixedWidth(28)
        info_button.setToolTip("Afficher le facteur eCO₂ et la source du matériau")
        info_button.clicked.connect(
            lambda _checked=False, material_combo=combo, button=info_button:
                self.show_material_info(material_combo, button)
        )

        layout.addWidget(combo, 1)
        layout.addWidget(info_button)
        selector.setLayout(layout)
        return selector

    def init_ui(self):
        main_layout = QVBoxLayout()

        self.form_layout = QFormLayout()
        self.required_fields = []
        self.solid_section_headers = []
        self.liquid_section_headers = []

        # Sélecteur de type
        self.add_section_header("Identification")
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Consommable solide", "Consommable liquide"])
        self.type_combo.currentIndexChanged.connect(self.on_type_changed)
        self.form_layout.addRow("Type d'objet :", self.type_combo)
        self.is_liquid = False  # par défaut

        self.nom_input = QLineEdit()
        self.brand_input = QLineEdit()
        self.ref_input = QLineEdit()
        self.nom_input.setPlaceholderText("Nom du consommable")
        self.brand_input.setPlaceholderText("Marque / fournisseur")
        self.ref_input.setPlaceholderText("Référence catalogue ou interne")

        # Définir la liste des matériaux avant toute création de ComboBox qui l'utilise
        if self.data_materials is not None:
            mats = self.data_materials['Materiau'].dropna().unique().tolist()
        else:
            mats = ["Polypropylène (PP)", "Polyéthylène (PE)"]

        # Second matériau (optionnel)
        self.masse2_input = QLineEdit()
        self.materiau2_combo = QComboBox()
        self.materiau2_combo.addItems(mats)

        # Emballage
        self.masse_emb_input = QLineEdit()
        self.mat_emb_combo = QComboBox()
        self.mat_emb_combo.addItems(mats)

        # Conditionnement
        self.masse_cond_input = QLineEdit()
        self.mat_cond_combo = QComboBox()
        self.mat_cond_combo.addItems(mats)
        self.nbr_cond_input = QLineEdit()
        self.nbr_cond_input.setValidator(QIntValidator(1, 999999, self))
        self.nbr_cond_input.setPlaceholderText("1 si vendu à l'unité")

        # Prix manuel
        self.price_mode_combo = QComboBox()
        self.price_mode_combo.addItems(["Prix par conditionnement", "Prix par unité"])
        self.price_input = QLineEdit()
        self.price_input.setValidator(QDoubleValidator(0.0, 999999999.0, 6, self))
        self.price_input.setPlaceholderText("Prix obligatoire")
        self.price_preview_label = QLabel("Prix unitaire calculé : —")
        self.price_preview_label.setStyleSheet("color: #4b5563;")

        self.price_row_widget = QWidget()
        price_layout = QHBoxLayout()
        price_layout.setContentsMargins(0, 0, 0, 0)
        price_layout.addWidget(self.price_mode_combo, 2)
        price_layout.addWidget(self.price_input, 1)
        self.price_row_widget.setLayout(price_layout)

        # Lien / Note
        self.lien_input = QLineEdit()

        # Instead of form_layout.addRow("Code NACRES:", self.nacres_input)
        self.nacres_combo = QComboBox()
        nacres_layout = QVBoxLayout()
        nacres_layout.setContentsMargins(0, 0, 0, 0)
        nacres_layout.addWidget(self.nacres_combo)

        search_layout = QHBoxLayout()
        search_label = QLabel("Rechercher un code NACRES:")
        search_layout.addWidget(search_label)
        self.nacres_search = QLineEdit()
        search_layout.addWidget(self.nacres_search)

        nacres_layout.addLayout(search_layout)
        self.nacres_widget = QWidget()
        self.nacres_widget.setLayout(nacres_layout)
        self.form_layout.addRow("Code NACRES:", self.nacres_widget)

        self.masse_input = QLineEdit()
        self.masse_input.setPlaceholderText("Optionnel, mais nécessaire pour calculer l'eCO₂ par masse")

        # Peupler la liste des matériaux depuis data_materials
        self.materiau_combo = QComboBox()
        self.materiau_combo.addItems(mats)

        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Nom, équipe, source documentaire...")

        self.materiau_row_widget = self.create_material_selector(self.materiau_combo)
        self.materiau2_row_widget = self.create_material_selector(self.materiau2_combo)
        self.mat_emb_row_widget = self.create_material_selector(self.mat_emb_combo)
        self.mat_cond_row_widget = self.create_material_selector(self.mat_cond_combo)

        self.form_layout.addRow("Consommable:", self.nom_input)
        self.form_layout.addRow("Marque:", self.brand_input)
        self.form_layout.addRow("Référence:", self.ref_input)

        self.add_section_header("Matériau consommable 1", mode="solid")
        self.form_layout.addRow("Matériau consommable 1:", self.materiau_row_widget)
        self.form_layout.addRow("Masse matériau 1 (g):", self.masse_input)

        self.add_section_header("Matériau consommable 2 (optionnel)", mode="solid")
        self.form_layout.addRow("Matériau consommable 2:", self.materiau2_row_widget)
        self.form_layout.addRow("Masse matériau 2 (g):", self.masse2_input)

        self.add_section_header("Emballage", mode="solid")
        self.form_layout.addRow("Matériau emballage:", self.mat_emb_row_widget)
        self.form_layout.addRow("Masse emballage (g):", self.masse_emb_input)

        self.add_section_header("Conditionnement et prix", mode="solid")
        self.form_layout.addRow("Nbr par conditionnement:", self.nbr_cond_input)
        self.form_layout.addRow("Matériau conditionnement:", self.mat_cond_row_widget)
        self.form_layout.addRow("Masse conditionnement (g):", self.masse_cond_input)
        self.form_layout.addRow("Prix:", self.price_row_widget)
        self.form_layout.addRow("", self.price_preview_label)

        self.register_required_field(self.type_combo, "Type d'objet")
        self.register_required_field(self.nacres_widget, "Code NACRES", control=self.nacres_combo)
        self.register_required_field(self.nom_input, "Consommable")
        self.register_required_field(self.brand_input, "Marque")
        self.register_required_field(self.ref_input, "Référence")
        self.register_required_field(self.nbr_cond_input, "Nbr par conditionnement")
        self.register_required_field(self.price_row_widget, "Prix", control=self.price_input)

        # --- Widgets spécifiques Liquide ---
        self.dens_input    = QLineEdit()
        self.conc_input    = QLineEdit()
        self.factor_input  = QLineEdit()
        self.uncert_input  = QLineEdit()
        self.vol_flacon_input = QLineEdit()
        self.vol_flacon_input.setPlaceholderText("ex: 1000 (mL) — optionnel")

        # Contenant (bouteille verre, plastique…)
        self.mat_contenant_liq_combo = QComboBox()
        self.mat_contenant_liq_combo.addItems([''] + mats)
        self.mat_contenant_liq_row = self.create_material_selector(self.mat_contenant_liq_combo)
        self.masse_contenant_liq_input = QLineEdit()
        self.masse_contenant_liq_input.setPlaceholderText("ex: 200 g (optionnel)")

        # Emballage (carton, film…) liquide
        self.mat_emb_liq_combo = QComboBox()
        self.mat_emb_liq_combo.addItems([''] + mats)
        self.mat_emb_liq_row = self.create_material_selector(self.mat_emb_liq_combo)
        self.masse_emb_liq_input = QLineEdit()
        self.masse_emb_liq_input.setPlaceholderText("ex: 50 g (optionnel)")

        self.add_section_header("Données liquide", mode="liquid")
        self.form_layout.addRow("Densité (g/mL):",      self.dens_input)
        self.form_layout.addRow("Concentration (mg/mL):", self.conc_input)
        self.form_layout.addRow("Facteur CO₂ (kg/kg):", self.factor_input)
        self.form_layout.addRow("Incertitude (%) :",    self.uncert_input)
        self.form_layout.addRow("Volume flacon (mL) :", self.vol_flacon_input)

        self.add_section_header("Contenant & emballage (optionnel)", mode="liquid")
        self.form_layout.addRow("Matériau contenant :", self.mat_contenant_liq_row)
        self.form_layout.addRow("Masse contenant (g) :", self.masse_contenant_liq_input)
        self.form_layout.addRow("Matériau emballage :", self.mat_emb_liq_row)
        self.form_layout.addRow("Masse emballage (g) :", self.masse_emb_liq_input)

        self.register_required_field(self.dens_input, "Densité")
        self.register_required_field(self.factor_input, "Facteur CO₂")

        self.add_section_header("Source et notes")
        self.form_layout.addRow("Lien / Note / Remarque:", self.lien_input)
        self.form_layout.addRow("Source/Signature:", self.source_input)
        self.register_required_field(self.source_input, "Source/Signature")

        # Masquer ces lignes initialement
        for w in (
            self.dens_input, self.conc_input, self.factor_input, self.uncert_input,
            self.vol_flacon_input,
            self.mat_contenant_liq_row, self.masse_contenant_liq_input,
            self.mat_emb_liq_row, self.masse_emb_liq_input,
        ):
            w.setVisible(False)

        form_container = QWidget()
        form_container.setLayout(self.form_layout)
        self.form_scroll_area = QScrollArea()
        self.form_scroll_area.setWidgetResizable(True)
        self.form_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.form_scroll_area.setMinimumHeight(280)
        self.form_scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.form_scroll_area.setWidget(form_container)
        main_layout.addWidget(self.form_scroll_area, 1)

        self.add_button = QPushButton("Ajouter l'objet")
        self.add_button.clicked.connect(self.ajouter_objet_utilisateur)
        main_layout.addWidget(self.add_button)

        export_import_layout = QHBoxLayout()
        self.export_button = QPushButton("⬆ Exporter la base de données")
        self.export_button.clicked.connect(self.export_database)
        self.import_button = QPushButton("⬇ Mise à jour de la base de données")
        self.import_button.clicked.connect(self.import_database)
        export_import_layout.addWidget(self.export_button)
        export_import_layout.addWidget(self.import_button)
        main_layout.addLayout(export_import_layout)

        # Tableau des données
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.set_table_visible_rows(4)

        # Appliquer le style pour avoir le texte en noir
        self.table.setStyleSheet("""
                                QTableWidget { 
                                    color: black; 
                                }
                                QHeaderView::section {
                                    color: black;
                                }
                            """)

        main_layout.addWidget(self.table, 0)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Applique la visibilité initiale (solide)
        self.update_form_visibility()
        self.nacres_search.textChanged.connect(self.filter_nacres_list)
        self.nacres_combo.currentIndexChanged.connect(self.update_required_indicators)
        self.type_combo.currentIndexChanged.connect(self.update_required_indicators)
        self.price_mode_combo.currentIndexChanged.connect(self.update_price_preview)
        self.price_input.textChanged.connect(self.update_price_preview)
        self.nbr_cond_input.textChanged.connect(self.update_price_preview)
        for field in (
            self.nom_input, self.brand_input, self.ref_input,
            self.nbr_cond_input, self.price_input, self.source_input,
            self.dens_input, self.factor_input
        ):
            field.textChanged.connect(self.update_required_indicators)
        self.load_nacres_list()
        self.update_required_indicators()
        self.update_price_preview()

    def on_type_changed(self, idx):
        """Bascule solide/liquide : met à jour visibilité + table."""
        self.is_liquid = (idx == 1)               # 0 = solide, 1 = liquide
        # Recharger le fichier HDF5 liquide à chaque bascule pour afficher les ajouts récents
        if self.is_liquid:
            self.data_liquids = self.load_liquid_df()
        self.update_form_visibility()             # masque/affiche les bons champs
        self.update_required_indicators()
        self.update_price_preview()
        self.afficher_donnees()                   # recharge la table avec le bon DF

    def load_nacres_list(self):
        if not os.path.exists(self.nacres_hdf5_file):
            print(f"[INFO] Fichier '{self.nacres_hdf5_file}' introuvable.")
            return

        try:
            df_nacres = pd.read_hdf(self.nacres_hdf5_file)
            self._all_nacres = []
            for _, row in df_nacres.iterrows():
                code = str(row.iloc[0])
                desc = str(row.iloc[1])
                self._all_nacres.append((code, desc))
            self.filter_nacres_list()
        except Exception as e:
            print(f"[ERROR] Impossible de charger la liste NACRES: {e}")

    def load_liquid_df(self):
        if os.path.exists(self.hdf5_liquids):
            df_liq = pd.read_hdf(self.hdf5_liquids)
        else:
            df_liq = pd.DataFrame(columns=self.columns_liquids)
        for col in self.columns_liquids:
            if col not in df_liq.columns:
                df_liq[col] = ""
        return df_liq

    def filter_nacres_list(self):
        search_text = self.nacres_search.text().strip().lower()
        self.nacres_combo.clear()
        self.nacres_combo.addItem("Sélectionnez un code NACRES...", None)
        for (code, desc) in self._all_nacres:
            if search_text in code.lower() or search_text in desc.lower():
                display_text = f"{code} - {desc}"
                self.nacres_combo.addItem(display_text, code)
        self.update_required_indicators()

    def show_material_info(self, material_combo, button):
        material_name = material_combo.currentText().strip()
        info_text = self.format_material_info(material_name)
        QToolTip.showText(
            QCursor.pos(),
            info_text,
            button,
            button.rect(),
            20000,
        )

    def format_material_info(self, material_name):
        if self.data_materials is None or self.data_materials.empty:
            return "Données matériaux non chargées."
        if not material_name:
            return "Aucun matériau sélectionné."

        mat_col = "Materiau"
        co2_col = "Equivalent CO₂ (kg eCO₂/kg)"
        uncertainty_col = "uncertainty"
        source_col = "Source"

        if mat_col not in self.data_materials.columns:
            return "Colonne matériau introuvable dans la base."

        mask = self.data_materials[mat_col].astype(str).str.strip() == material_name
        rows = self.data_materials[mask]
        if rows.empty:
            return f"Matériau introuvable : {html.escape(material_name)}"

        row = rows.iloc[0]

        def clean(value):
            if pd.isna(value):
                return ""
            text = str(value).strip()
            return "" if text.lower() in ("", "nan", "none", "n/a") else text

        co2_value = clean(row.get(co2_col, ""))
        uncertainty = clean(row.get(uncertainty_col, ""))
        source = clean(row.get(source_col, ""))

        lines = [
            f"<b>{html.escape(material_name)}</b>",
            f"Facteur : <b>{html.escape(co2_value or '/')} kg eCO₂/kg</b>",
        ]
        if uncertainty:
            lines.append(f"Incertitude : {html.escape(uncertainty)}")
        lines.append("Source :")
        lines.append(self.linkify_source(source) if source else "/")
        return "<br>".join(lines)

    def linkify_source(self, source):
        source_text = str(source)
        source_text = self.add_known_source_links(source_text)
        parts = re.split(r"(https?://[^\s<]+)", source_text)
        html_parts = []
        for part in parts:
            if part.startswith(("http://", "https://")):
                trailing = ""
                while part and part[-1] in ".,;)":
                    trailing = part[-1] + trailing
                    part = part[:-1]
                safe_url = html.escape(part)
                html_parts.append(f'<a href="{safe_url}">{safe_url}</a>{html.escape(trailing)}')
            else:
                html_parts.append(html.escape(part))
        return "".join(html_parts).replace("DOI: ", "DOI : ")

    @staticmethod
    def add_known_source_links(source_text):
        additions = []
        if "Base Empreinte" in source_text and "base-empreinte.ademe.fr" not in source_text:
            additions.append("https://base-empreinte.ademe.fr")
        if "France Stratégie" in source_text and "strategie.gouv.fr" not in source_text:
            additions.append("https://www.strategie.gouv.fr")

        doi_match = re.search(r"DOI:\s*([^\s]+)", source_text)
        if doi_match:
            doi = doi_match.group(1).rstrip(".,;)")
            doi_url = f"https://doi.org/{doi}"
            if doi_url not in source_text:
                additions.append(doi_url)

        if additions:
            return f"{source_text} - " + " - ".join(additions)
        return source_text

    def register_required_field(self, field_widget, label_text, control=None):
        label = self.form_layout.labelForField(field_widget)
        if label is None:
            return
        self.required_fields.append({
            "field": field_widget,
            "control": control or field_widget,
            "label": label,
            "label_text": label_text,
        })

    def is_required_field_filled(self, control):
        if isinstance(control, QLineEdit):
            return bool(control.text().strip())
        if isinstance(control, QComboBox):
            if control.currentIndex() < 0:
                return False
            data = control.currentData()
            if data is None:
                current_text = control.currentText().strip()
                return bool(current_text) and not current_text.startswith("Sélectionnez")
            return bool(str(data).strip())
        return True

    def set_required_style(self, control, filled):
        if filled:
            control.setStyleSheet("")
            return

        control.setStyleSheet(
            "border: 2px solid #dc2626; border-radius: 4px; "
            "background-color: #fff5f5;"
        )

    def update_required_indicators(self):
        for item in self.required_fields:
            field = item["field"]
            control = item["control"]
            label = item["label"]
            label_text = item["label_text"]
            active = not field.isHidden()
            if self.is_liquid and label_text in {"Marque", "Nbr par conditionnement"}:
                active = False

            if not active:
                label.setText(f"{label_text}:")
                label.setStyleSheet("")
                control.setStyleSheet("")
                continue

            filled = self.is_required_field_filled(control)
            if filled:
                label.setText(f"✓ {label_text}:")
                label.setStyleSheet("color: #15803d; font-weight: 600;")
            else:
                label.setText(f"✗ {label_text}:")
                label.setStyleSheet("color: #dc2626; font-weight: 600;")
            self.set_required_style(control, filled)

    @staticmethod
    def _parse_optional_float(raw_text, field_name):
        text = str(raw_text).strip().replace(',', '.')
        if text == "" or text.lower() in ("n/a", "nan", "none"):
            return ""
        try:
            value = float(text)
        except ValueError:
            raise ValueError(f"{field_name} doit être un nombre valide.")
        if value < 0:
            raise ValueError(f"{field_name} doit être positif.")
        return text

    def compute_manual_price_fields(self, nbr_cond):
        price_text = self.price_input.text().strip().replace(',', '.')
        if not price_text:
            return {"Prix du conditionnement": ""}

        try:
            price = float(price_text)
        except ValueError:
            raise ValueError("Le prix doit être un nombre valide.")
        if price < 0:
            raise ValueError("Le prix doit être positif.")

        if self.price_mode_combo.currentText() == "Prix par unité":
            prix_conditionnement = price * nbr_cond
        else:
            prix_conditionnement = price

        return {"Prix du conditionnement": prix_conditionnement}

    def update_price_preview(self):
        if self.is_liquid:
            self.price_preview_label.setText("Prix unitaire calculé : /")
            self.price_preview_label.setStyleSheet("color: #4b5563;")
            return

        price_text = self.price_input.text().strip().replace(',', '.')
        nbr_text = self.nbr_cond_input.text().strip()
        if not price_text:
            self.price_preview_label.setText("Prix unitaire calculé : —")
            self.price_preview_label.setStyleSheet("color: #4b5563;")
            return

        try:
            price = float(price_text)
            nbr_cond = int(nbr_text)
            if price < 0 or nbr_cond <= 0:
                raise ValueError
        except ValueError:
            self.price_preview_label.setText("Prix unitaire calculé : valeur à vérifier")
            self.price_preview_label.setStyleSheet("color: #dc2626; font-weight: 600;")
            return

        if self.price_mode_combo.currentText() == "Prix par unité":
            prix_unitaire = price
            prix_conditionnement = price * nbr_cond
        else:
            prix_conditionnement = price
            prix_unitaire = price / nbr_cond

        self.price_preview_label.setText(
            f"Prix unitaire calculé : {prix_unitaire:.4g} € "
            f"| Prix du conditionnement : {prix_conditionnement:.4g} €"
        )
        self.price_preview_label.setStyleSheet("color: #15803d; font-weight: 600;")

    def verifier_existence_objet(self, nom, reference, code_nacres, ignore_index=None):
        df = self.data
        if ignore_index is not None:
            df = df.drop(index=ignore_index, errors="ignore")

        if not df[df["Consommable"] == nom].empty:
            return f"Un objet avec le nom '{nom}' existe déjà."

        if not df[(df["Référence"] == reference) & (df["Code NACRES"] == code_nacres)].empty:
            return f"La combinaison Référence='{reference}' et Code NACRES='{code_nacres}' existe déjà."

        return None

    def ajouter_objet_utilisateur(self):
        is_liq = self.is_liquid
        nom = self.nom_input.text().strip()
        marque = self.brand_input.text().strip()
        reference = self.ref_input.text().strip()
        nacres = self.nacres_combo.currentData()
        masse_str = self.masse_input.text().strip().replace(',', '.')
        materiau = self.materiau_combo.currentText()
        masse2_str   = self.masse2_input.text().strip().replace(',', '.')
        materiau2    = self.materiau2_combo.currentText()
        masse_emb_str= self.masse_emb_input.text().strip().replace(',', '.')
        mat_emb      = self.mat_emb_combo.currentText()
        masse_cond_str = self.masse_cond_input.text().strip().replace(',', '.')
        mat_cond     = self.mat_cond_combo.currentText()
        nbr_cond     = self.nbr_cond_input.text().strip()
        price_text   = self.price_input.text().strip()
        lien_note    = self.lien_input.text().strip()
        source = self.source_input.text().strip()
        self.update_required_indicators()

        if is_liq:
            dens       = self.dens_input.text().strip().replace(',', '.')
            conc       = self.conc_input.text().strip().replace(',', '.')
            facteur    = self.factor_input.text().strip().replace(',', '.')
            incert     = self.uncert_input.text().strip().replace(',', '.')
            vol_flacon = self.vol_flacon_input.text().strip().replace(',', '.')
            mat_cont   = self.mat_contenant_liq_combo.currentText().strip()
            masse_cont = self.masse_contenant_liq_input.text().strip().replace(',', '.')
            mat_emb_liq = self.mat_emb_liq_combo.currentText().strip()
            masse_emb_liq = self.masse_emb_liq_input.text().strip().replace(',', '.')
        else:
            dens = conc = facteur = incert = ""

        if is_liq:
            required_ok = all([nom, reference, nacres, dens, facteur, source])
        else:
            required_ok = all([nom, marque, reference, nacres, nbr_cond, price_text, source])
        if not required_ok:
            QMessageBox.warning(self, "Erreur", "Tous les champs obligatoires doivent être remplis.")
            return

        nbr_cond_value = None
        if not is_liq:
            try:
                nbr_cond_value = int(nbr_cond)
                if nbr_cond_value <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Erreur",
                    "Le nombre par conditionnement doit être un entier positif."
                )
                return

            try:
                masse_str = self._parse_optional_float(masse_str, "La masse unitaire")
                masse2_str = self._parse_optional_float(masse2_str, "La masse unitaire 2")
                masse_emb_str = self._parse_optional_float(masse_emb_str, "La masse emballage")
                masse_cond_str = self._parse_optional_float(masse_cond_str, "La masse conditionnement")
                price_fields = self.compute_manual_price_fields(nbr_cond_value)
            except ValueError as exc:
                QMessageBox.warning(self, "Erreur", str(exc))
                return
        else:
            price_fields = {}

        ignore_index = None if is_liq else self.prefill_row_index
        erreur = self.verifier_existence_objet(nom, reference, nacres, ignore_index=ignore_index)
        if erreur:
            QMessageBox.warning(self, "Erreur", erreur)
            return

        was_update = (
            not is_liq
            and self.prefill_row_index is not None
            and self.prefill_row_index in self.data.index
        )

        if is_liq:
            nouvel_objet = {
                "Produit": nom,
                "Type": "Liquide",
                "Code NACRES": nacres,
                "CAS": reference,
                "Référence": reference,
                "Unité": "mL",
                "Densité (g/mL)": dens,
                "Concentration (mg/mL)": conc,
                "Facteur CO₂ (kg CO₂e/kg)": facteur,
                "Incertitude (%)": incert,
                "Volume flacon (mL)": vol_flacon or None,
                "Matériau contenant": mat_cont,
                "Masse contenant (g)": masse_cont or None,
                "Matériau emballage": mat_emb_liq,
                "Masse emballage (g)": masse_emb_liq or None,
                "Source/Signature": source,
                "date d'ajout": date.today().isoformat(),
                "Note": lien_note
            }
        else:
            nouvel_objet = {col: "" for col in self.columns}
            if self.prefill_row_index is not None and self.prefill_row_index in self.data.index:
                existing = self.data.loc[self.prefill_row_index].to_dict()
                nouvel_objet.update(existing)

            nouvel_objet.update({
                "Consommable": nom,
                "Marque": marque,
                "Référence": reference,
                "Code CAS": "",
                "Catégorie": "Consommable",
                "Code NACRES": nacres,
                "Masse unitaire (g)": masse_str,
                "Matériau consommable": materiau,
                "Masse unitaire deuxieme materiaux (g)": masse2_str,
                "Matériau deuxieme materiaux": materiau2,
                "Masse unitaire troisième materiaux (g)": "",
                "Matériau troisième materiaux": "",
                "Masse emballage unitaire (g)": masse_emb_str,
                "Matériau emballage": mat_emb,
                "Masse condionnement (g)": masse_cond_str,
                "Matériau conditionnement": mat_cond,
                "Nbr par conditionnement": nbr_cond_value,
                "date d'ajout": date.today().isoformat(),
                "Lien / Note / Remarque": lien_note,
                "Source/Signature": source
            })

            if price_fields:
                nouvel_objet.update(price_fields)

        if is_liq:
            self.save_liquid(nouvel_objet)
        else:
            if self.prefill_row_index is not None and self.prefill_row_index in self.data.index:
                for col in self.columns:
                    self.data.at[self.prefill_row_index, col] = nouvel_objet.get(col, "")
            else:
                self.data = self.ajouter_objet_df(self.data, nouvel_objet)
            self.sauvegarder_donnees()

        # Efface les champs
        self.nom_input.clear()
        self.brand_input.clear()
        self.ref_input.clear()
        self.masse_input.clear()
        self.materiau_combo.setCurrentIndex(0)
        self.masse2_input.clear()
        self.materiau2_combo.setCurrentIndex(0)
        self.masse_emb_input.clear()
        self.mat_emb_combo.setCurrentIndex(0)
        self.masse_cond_input.clear()
        self.mat_cond_combo.setCurrentIndex(0)
        self.nbr_cond_input.clear()
        self.price_mode_combo.setCurrentIndex(0)
        self.price_input.clear()
        self.lien_input.clear()
        self.source_input.clear()
        self.nacres_combo.setCurrentIndex(0 if self.nacres_combo.count() else -1)
        self.dens_input.clear()
        self.conc_input.clear()
        self.factor_input.clear()
        self.uncert_input.clear()
        self.vol_flacon_input.clear()
        self.masse_contenant_liq_input.clear()
        self.masse_emb_liq_input.clear()
        self.mat_contenant_liq_combo.setCurrentIndex(0)
        self.mat_emb_liq_combo.setCurrentIndex(0)
        self.prefill_row_index = None
        self.add_button.setText("Ajouter l'objet")
        self.update_required_indicators()
        self.update_price_preview()

        action = "mis à jour" if was_update else "ajouté"
        QMessageBox.information(self, "Succès", f"L'objet '{nom}' a été {action} avec succès.")
        self.data_added.emit()
        self.afficher_donnees()

    def save_liquid(self, obj_dict):
        """Ajoute une ligne au fichier HDF5 des liquides."""
        # Charger ou créer DF
        if os.path.exists(self.hdf5_liquids):
            try:
                df_liq = pd.read_hdf(self.hdf5_liquids)
            except Exception:
                df_liq = pd.DataFrame(columns=self.columns_liquids)
        else:
            df_liq = pd.DataFrame(columns=self.columns_liquids)

        # Assurer toutes les colonnes
        for col in self.columns_liquids:
            if col not in df_liq.columns:
                df_liq[col] = ""

        # Mise à jour de la ligne existante si mode enrichissement
        if getattr(self, '_prefill_liq_produit', None):
            mask = df_liq["Produit"].astype(str).str.strip() == self._prefill_liq_produit
            if mask.any():
                idx = df_liq[mask].index[0]
                for col, val in obj_dict.items():
                    if col not in df_liq.columns:
                        df_liq[col] = ""
                    df_liq.at[idx, col] = val
                self._prefill_liq_produit = None
                df_liq.to_hdf(self.hdf5_liquids, key='data', mode='w')
                self.data_liquids = df_liq
                if self.is_liquid:
                    self.afficher_donnees()
                return

        new_line = pd.DataFrame([obj_dict]).reindex(columns=self.columns_liquids)
        df_liq = pd.concat([df_liq, new_line], ignore_index=True)
        df_liq.to_hdf(self.hdf5_liquids, key='data', mode='w')
        self.data_liquids = df_liq
        if self.is_liquid:
            self.afficher_donnees()

    def ajouter_objet_df(self, df, objet):
        nouvel_objet = pd.DataFrame([objet])
        nouvel_objet = nouvel_objet.reindex(columns=self.columns)

        if df.empty:
            return nouvel_objet
        else:
            return pd.concat([df, nouvel_objet], ignore_index=True)

    def afficher_donnees(self):
        # Réinitialiser le tableau
        self.table.clearContents()
        if self.is_liquid:
            df, cols = self.data_liquids, self.columns_liquids
        else:
            df, cols = self.data, self.columns

        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)

        self.table.setRowCount(len(df))
        for i, (_, row) in enumerate(df.iterrows()):
            for j, col in enumerate(cols):
                self.table.setItem(i, j, QTableWidgetItem(str(row.get(col, ""))))
        self.table.resizeColumnsToContents()
        self.set_table_visible_rows(4)

    def set_table_visible_rows(self, row_count=4):
        header_height = (
            self.table.horizontalHeader().height()
            or self.table.horizontalHeader().sizeHint().height()
        )
        row_height = self.table.verticalHeader().defaultSectionSize()
        scrollbar_height = self.table.horizontalScrollBar().sizeHint().height()
        frame_height = self.table.frameWidth() * 2
        table_height = header_height + row_height * row_count + scrollbar_height + frame_height + 6
        self.table.setMinimumHeight(table_height)
        self.table.setMaximumHeight(table_height)
    
    def update_form_visibility(self):
        """Montre/masque les champs en fonction de self.is_liquid."""
        for header in self.solid_section_headers:
            header.setVisible(not self.is_liquid)
        for header in self.liquid_section_headers:
            header.setVisible(self.is_liquid)

        # Champs propres aux solides
        for w in (
            self.masse_input, self.materiau_row_widget,
            self.masse2_input, self.materiau2_row_widget,
            self.masse_emb_input, self.mat_emb_row_widget,
            self.masse_cond_input, self.mat_cond_row_widget,
            self.nbr_cond_input,
            self.price_row_widget,
            self.price_preview_label
        ):
            lab = self.form_layout.labelForField(w)
            if lab:
                lab.setVisible(not self.is_liquid)
            w.setVisible(not self.is_liquid)

        # Champs propres aux liquides
        for w in (
            self.dens_input, self.conc_input,
            self.factor_input, self.uncert_input,
            self.vol_flacon_input,
            self.mat_contenant_liq_row, self.masse_contenant_liq_input,
            self.mat_emb_liq_row, self.masse_emb_liq_input,
        ):
            lab = self.form_layout.labelForField(w)
            if lab:
                lab.setVisible(self.is_liquid)
            w.setVisible(self.is_liquid)
        self.update_required_indicators()
        self.update_price_preview()

    def export_database(self):
        """
        Exporte la base de données consommables vers un fichier HDF5 ou CSV
        choisi par l'utilisateur.
        """
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Exporter la base de données",
            "base_consommables_LABeCO2.hdf5",
            "HDF5 (*.hdf5 *.h5);;CSV (*.csv)"
        )
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                self.data.to_csv(path, index=False, encoding="utf-8")
            else:
                self.data.to_hdf(path, key="data", mode="w", complevel=5)
            QMessageBox.information(
                self, "Export réussi",
                f"{len(self.data)} consommables exportés vers :\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur export", f"Impossible d'exporter :\n{e}")

    def import_database(self):
        """
        Importe une base de données mise à jour (HDF5) pour remplacer la base locale.
        Un backup automatique est créé avant le remplacement.
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Charger une mise à jour de la base de données",
            "",
            "HDF5 (*.hdf5 *.h5)"
        )
        if not path:
            return

        try:
            new_df = pd.read_hdf(path)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de lire le fichier :\n{e}")
            return

        # Vérification minimale : la colonne Consommable doit exister
        if "Consommable" not in new_df.columns and "Code NACRES" not in new_df.columns:
            QMessageBox.warning(
                self, "Format invalide",
                "Le fichier ne semble pas être une base de consommables LABeCO2 valide."
            )
            return

        confirm = QMessageBox.question(
            self, "Confirmer la mise à jour",
            f"Remplacer la base actuelle ({len(self.data)} entrées) "
            f"par le nouveau fichier ({len(new_df)} entrées) ?\n\n"
            f"Un backup sera créé automatiquement.",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            import shutil
            backup_path = self.hdf5_file + ".backup"
            if os.path.exists(self.hdf5_file):
                shutil.copy2(self.hdf5_file, backup_path)

            new_df.to_hdf(self.hdf5_file, key="data", mode="w", complevel=5)
            self.data = new_df
            # Harmoniser les colonnes manquantes
            for col in self.columns:
                if col not in self.data.columns:
                    self.data[col] = ""

            self.afficher_donnees()
            self.data_added.emit()  # recharge dans la fenêtre principale

            QMessageBox.information(
                self, "Mise à jour réussie",
                f"Base mise à jour : {len(new_df)} consommables chargés.\n"
                f"Backup sauvegardé : {backup_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de mettre à jour la base :\n{e}")

    def prefill_consumable(self, code_nacres, consommable_name, source="solid"):
        """
        Pré-remplit le formulaire avec les données du consommable sélectionné
        dans la fenêtre principale.  Si une ligne existe déjà, tous les champs
        sont remplis (mode enrichissement). Gère solides et liquides.
        """
        self.prefill_row_index = None
        self._prefill_liq_produit = None
        self.add_button.setText("Ajouter l'objet")

        def _clean_value(value):
            if pd.isna(value):
                return ""
            text = str(value).strip()
            return "" if text.lower() in ("", "nan", "n/a", "none") else text

        # ── NACRES : extraire le préfixe 4 chars ─────────────────────────────
        code4 = str(code_nacres).strip().upper()[:4]

        # ── Liquide ──────────────────────────────────────────────────────────
        if source == "liquid":
            self.type_combo.blockSignals(True)
            self.type_combo.setCurrentIndex(1)
            self.type_combo.blockSignals(False)
            self.is_liquid = True
            self.data_liquids = self.load_liquid_df()
            self.update_form_visibility()
            self.afficher_donnees()

            self.nom_input.setText(consommable_name)

            # Code NACRES
            idx = self.nacres_combo.findData(code4)
            if idx == -1:
                for i in range(self.nacres_combo.count()):
                    if self.nacres_combo.itemText(i).startswith(code4):
                        idx = i
                        break
            if idx != -1:
                self.nacres_combo.setCurrentIndex(idx)

            # Chercher la ligne dans data_liquids
            df_liq = self.data_liquids
            mask = df_liq["Produit"].astype(str).str.strip() == consommable_name.strip()
            rows = df_liq[mask]

            if not rows.empty:
                row = rows.iloc[0]
                self._prefill_liq_produit = consommable_name.strip()
                self.add_button.setText("Enregistrer les informations")

                def _fill(field, col):
                    v = _clean_value(row.get(col, ""))
                    if v:
                        field.setText(v)

                _fill(self.dens_input,               "Densité (g/mL)")
                _fill(self.conc_input,               "Concentration (mg/mL)")
                _fill(self.factor_input,             "Facteur CO₂ (kg CO₂e/kg)")
                _fill(self.uncert_input,             "Incertitude (%)")
                _fill(self.vol_flacon_input,         "Volume flacon (mL)")
                _fill(self.masse_contenant_liq_input,"Masse contenant (g)")
                _fill(self.masse_emb_liq_input,      "Masse emballage (g)")
                _fill(self.source_input,             "Source/Signature")
                _fill(self.lien_input,               "Note")

                for combo, col in [
                    (self.mat_contenant_liq_combo, "Matériau contenant"),
                    (self.mat_emb_liq_combo,       "Matériau emballage"),
                ]:
                    val = _clean_value(row.get(col, ""))
                    i = combo.findText(val)
                    if i != -1:
                        combo.setCurrentIndex(i)

                # Sélectionner la ligne dans le tableau
                for r in range(self.table.rowCount()):
                    item = self.table.item(r, 0)
                    if item and item.text().strip() == consommable_name.strip():
                        self.table.selectRow(r)
                        break
            return

        # ── Solide ───────────────────────────────────────────────────────────
        self.type_combo.setCurrentIndex(0)

        # ── Nom ──────────────────────────────────────────────────────────────
        self.nom_input.setText(consommable_name)

        # ── Code NACRES ───────────────────────────────────────────────────────
        code4 = str(code_nacres).strip().upper()
        idx = self.nacres_combo.findData(code4)
        if idx == -1:
            # Chercher par texte si findData échoue
            for i in range(self.nacres_combo.count()):
                if self.nacres_combo.itemText(i).startswith(code4):
                    idx = i
                    break
        if idx != -1:
            self.nacres_combo.setCurrentIndex(idx)

        # ── Données existantes dans le HDF5 ───────────────────────────────────
        mask = (
            (self.data["Code NACRES"].astype(str).str.strip().str.upper() == code4) &
            (self.data["Consommable"].astype(str).str.strip() == consommable_name.strip())
        )
        rows = self.data[mask]

        if not rows.empty:
            row = rows.iloc[0]
            self.prefill_row_index = rows.index[0]
            self.add_button.setText("Enregistrer les informations")
            self.brand_input.setText(_clean_value(row.get("Marque", "")) or _clean_value(row.get("marque_ijm", "")))
            self.ref_input.setText(_clean_value(row.get("Référence", "")) or _clean_value(row.get("code_ijm", "")))

            def _fill(field, col):
                v = _clean_value(row.get(col, ""))
                if v:
                    field.setText(v)

            _fill(self.masse_input,     "Masse unitaire (g)")
            _fill(self.masse2_input,    "Masse unitaire deuxieme materiaux (g)")
            _fill(self.masse_emb_input, "Masse emballage unitaire (g)")
            _fill(self.masse_cond_input,"Masse condionnement (g)")
            _fill(self.nbr_cond_input,  "Nbr par conditionnement")
            if not self.nbr_cond_input.text().strip():
                _fill(self.nbr_cond_input, "nb_unites_ijm")
            _fill(self.lien_input,      "Lien / Note / Remarque")
            _fill(self.source_input,    "Source/Signature")

            prix_conditionnement = (
                _clean_value(row.get("Prix du conditionnement", ""))
                or _clean_value(row.get("prix_ht_ijm", ""))
            )
            prix_unitaire = _clean_value(row.get("prix_unitaire_ijm", ""))
            if prix_conditionnement:
                self.price_mode_combo.setCurrentText("Prix par conditionnement")
                self.price_input.setText(prix_conditionnement)
            elif prix_unitaire:
                self.price_mode_combo.setCurrentText("Prix par unité")
                self.price_input.setText(prix_unitaire)

            for combo, col in [
                (self.materiau_combo,  "Matériau consommable"),
                (self.materiau2_combo, "Matériau deuxieme materiaux"),
                (self.mat_emb_combo,   "Matériau emballage"),
                (self.mat_cond_combo,  "Matériau conditionnement"),
            ]:
                val = _clean_value(row.get(col, ""))
                i = combo.findText(val)
                if i != -1:
                    combo.setCurrentIndex(i)

            # Sélectionner et scroller jusqu'à la ligne dans le tableau
            for row_idx in range(self.table.rowCount()):
                item = self.table.item(row_idx, 0)  # colonne Consommable
                if item and item.text().strip() == consommable_name.strip():
                    self.table.selectRow(row_idx)
                    self.table.scrollToItem(item)
                    break
        else:
            # Consommable IJM-only : pré-remplir ce qu'on sait depuis data_masse étendu
            # (marque dans la colonne Marque si dispo)
            full_data = self.data  # data déjà chargée depuis HDF5 complet
            mask2 = full_data["Code NACRES"].astype(str).str.strip().str.upper() == code4
            ijm_rows = full_data[mask2]
            name_match = ijm_rows[
                ijm_rows["Consommable"].astype(str).str.strip() == consommable_name.strip()
            ]
            if not name_match.empty:
                row2 = name_match.iloc[0]
                self.brand_input.setText(_clean_value(row2.get("Marque", "")) or _clean_value(row2.get("marque_ijm", "")))
                self.ref_input.setText(_clean_value(row2.get("Référence", "")) or _clean_value(row2.get("code_ijm", "")))

                prix_conditionnement = (
                    _clean_value(row2.get("Prix du conditionnement", ""))
                    or _clean_value(row2.get("prix_ht_ijm", ""))
                )
                prix_unitaire = _clean_value(row2.get("prix_unitaire_ijm", ""))
                if prix_conditionnement:
                    self.price_mode_combo.setCurrentText("Prix par conditionnement")
                    self.price_input.setText(prix_conditionnement)
                elif prix_unitaire:
                    self.price_mode_combo.setCurrentText("Prix par unité")
                    self.price_input.setText(prix_unitaire)

        self.update_required_indicators()
        self.update_price_preview()

    def calculer_eCO2_via_masse(self, consommable_name, quantite):
        """
        Calcule l'eCO2 total pour un consommable donné en additionnant :
          - matériau principal
          - deuxième matériau (si masse > 0)
          - emballage
          - conditionnement (divisé par Nbr par conditionnement)

        :param consommable_name: str, nom du consommable dans self.data
        :param quantite: int, quantité d'unités
        """
        if self.data.empty:
            QMessageBox.warning(self, "Erreur", "Aucun consommable disponible.")
            return

        if not isinstance(quantite, int) or quantite <= 0:
            QMessageBox.warning(self, "Erreur", "La quantité doit être un entier positif.")
            return

        if self.data_materials is None:
            QMessageBox.warning(self, "Erreur", "Les données matériaux ne sont pas chargées.")
            return

        rows = self.data[self.data["Consommable"] == consommable_name]
        if rows.empty:
            QMessageBox.warning(self, "Erreur", f"Consommable '{consommable_name}' introuvable.")
            return
        last_obj = rows.iloc[0]

        # Rassemble toutes les paires (masse, matériau)
        # La colonne CO2 dans data_materials s'appelle "Equivalent CO₂ (kg eCO₂/kg)"
        CO2_COL = "Equivalent CO\u2082 (kg eCO\u2082/kg)"
        composants = [
            ("Masse unitaire (g)", "Matériau consommable"),
            ("Masse unitaire deuxieme materiaux (g)", "Matériau deuxieme materiaux"),
            ("Masse emballage unitaire (g)", "Matériau emballage"),
            ("Masse condionnement (g)", "Matériau conditionnement"),
        ]

        total_mass_kg = 0.0
        total_eCO2 = 0.0
        details = []

        for col_masse, col_mat in composants:
            masse_g = last_obj.get(col_masse, 0)
            try:
                masse_g = float(masse_g)
            except (ValueError, TypeError):
                masse_g = 0.0
            materiau = str(last_obj.get(col_mat, "")).strip()

            if masse_g <= 0 or materiau == "" or pd.isna(masse_g):
                continue

            # Cas conditionnement : diviser par Nb par cond.
            if col_masse == "Masse condionnement (g)":
                nb = last_obj.get("Nbr par conditionnement", 1)
                try:
                    nb = float(nb) if nb else 1
                    if nb > 0:
                        masse_g /= nb
                except (ValueError, TypeError):
                    pass

            masse_kg = masse_g / 1000.0 * quantite
            total_mass_kg += masse_kg

            # Chercher facteur — colonne correcte du DataFrame data_materials
            mat_row = self.data_materials[self.data_materials['Materiau'] == materiau]
            if mat_row.empty:
                details.append(f"{materiau}: facteur inconnu → ignoré")
                continue
            facteur = float(mat_row[CO2_COL].iloc[0])
            eCO2 = masse_kg * facteur
            total_eCO2 += eCO2
            details.append(f"{materiau}: {masse_kg:.4f} kg × {facteur:.2f} = {eCO2:.3f} kg")

        details_str = "\n".join(details) if details else "Aucun composant carbone calculé."
        QMessageBox.information(
            self, "Calcul eCO₂ via masse",
            f"Consommable: {last_obj['Consommable']}\n"
            f"Quantité: {quantite}\n"
            f"Masse totale: {total_mass_kg:.4f} kg\n"
            f"Détails:\n{details_str}\n"
            f"eCO₂ total: {total_eCO2:.4f} kg CO₂e"
        )
