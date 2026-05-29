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
import logging
import sqlite3
from datetime import date
import pandas as pd
from PySide6.QtWidgets import (
    QMainWindow, QMessageBox, QVBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QWidget, QComboBox, QHBoxLayout, QLabel, QFileDialog, QToolTip,
    QScrollArea, QSizePolicy, QListView
)
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QDoubleValidator, QIntValidator
from ui.display_utils import looks_like_liquid_commercial_product
from ui.nacres_metadata import load_nacres_options
from ui.sqlite_legacy_adapter import SQLITE_ID_COL, load_legacy_dataframes
from ui.sqlite_writer import (
    normalize_key,
    upsert_commercial_product,
    upsert_liquid_factor,
    upsert_material_factor,
)

logger = logging.getLogger(__name__)
SQLITE_PATH_ENV_VAR = "LABECO2_SQLITE_PATH"
_NACRES_NEW_NO_FE_COLOR = QColor(255, 210, 150)
_NACRES_NEW_NO_FE_TOOLTIP = (
    "Nouveau code NACRES 2026 : le projet GES 1point5 n'a pas encore défini "
    "de facteur d'émission pour cette catégorie."
)


def clean_sqlite_id(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


class DataMassWindow(QMainWindow):
    data_added = Signal()

    MODE_SOLID_CONSUMABLE = "solid_consumable"
    MODE_LIQUID_CONSUMABLE = "liquid_consumable"
    MODE_SOLID_FACTOR = "solid_factor"
    MODE_LIQUID_FACTOR = "liquid_factor"
    PRICE_MODE_PACK = "Prix du conditionnement vendu"
    PRICE_MODE_UNIT = "Prix par unité vendue"
    COLUMN_DISPLAY_LABELS = {
        "Consommable": "Consommable / produit commercial",
        "Masse unitaire (g)": "Masse du consommable solide par unité (g)",
        "Matériau consommable": "Matériau principal du consommable",
        "Masse unitaire deuxieme materiaux (g)": "Masse du matériau secondaire par unité (g)",
        "Matériau deuxieme materiaux": "Matériau secondaire du consommable",
        "Masse unitaire troisième materiaux (g)": "Masse du troisième matériau par unité (g)",
        "Matériau troisième materiaux": "Troisième matériau du consommable",
        "Masse emballage unitaire (g)": "Masse de l'emballage secondaire (g)",
        "Matériau emballage": "Matériau de l'emballage secondaire",
        "Nbr par emballage secondaire": "Unités partageant l'emballage secondaire",
        "Masse condionnement (g)": "Masse du conditionnement primaire complet ou du contenant vide (g)",
        "Matériau conditionnement": "Matériau du conditionnement primaire ou du contenant",
        "Nbr par conditionnement": "Unités par conditionnement vendu",
        "Prix du conditionnement": "Prix du conditionnement vendu (€ HT)",
        "Unité liquide": "Unité du consommable liquide",
        "Volume flacon (mL)": "Volume vendu par unité de consommable (mL)",
        "Facteur liquide source": "Facteur liquide / solvant utilisé",
        "condt_ijm": "Conditionnement vendu catalogue IJM",
        "designation_ijm": "Désignation catalogue IJM",
        "code_ijm": "Code catalogue IJM",
        "marque_ijm": "Marque catalogue IJM",
        "score_match": "Score de rapprochement catalogue",
        "Produit": "Facteur liquide / solvant",
        "Matériau contenant": "Matériau du contenant",
        "Masse contenant (g)": "Masse du contenant vide (g)",
        "Masse emballage (g)": "Masse de l'emballage secondaire (g)",
        "Materiau": "Matériau",
        "Equivalent CO₂ (kg eCO₂/kg)": "Facteur CO₂ matériau (kg eCO₂/kg)",
        "uncertainty": "Incertitude",
    }

    def __init__(self, parent=None, data_materials=None, base_path=None,
                 user_path=None, prefill_code=None, prefill_name=None,
                 prefill_source="solid", initial_mode=None, mode_filter="consumable",
                 sqlite_path=None, prefill_source_url=""):
        super().__init__(parent)

        self.mode_filter = mode_filter or "consumable"
        self.initial_mode = initial_mode
        self.setWindowTitle(
            "Gestion des facteurs d'émission"
            if self.mode_filter == "factor" else
            "Gestion des consommables"
        )
        self.setGeometry(100, 100, 860, 620)
        self.setMinimumSize(760, 520)

        # Résolution du base_path compatible PyInstaller
        if base_path is None:
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        if user_path is None:
            user_path = base_path
        self._user_path = user_path
        self.sqlite_path = sqlite_path or os.environ.get(SQLITE_PATH_ENV_VAR)
        if not self.sqlite_path:
            raise ValueError("DataMassWindow nécessite un chemin SQLite.")

        self._all_nacres = []

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
            "Nbr par emballage secondaire",
            "Masse condionnement (g)",
            "Matériau conditionnement",
            "Nbr par conditionnement",
            "Prix du conditionnement",
            "Unité liquide",
            "Volume flacon (mL)",
            "Facteur liquide source",
            "date d'ajout",
            "Source",
            "Signature",
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
            "Source",
            "Signature",
            "date d'ajout",
            "Note",
        ]

        self.columns_materials = [
            "Materiau",
            "Equivalent CO₂ (kg eCO₂/kg)",
            "uncertainty",
            "Source",
            "Signature",
        ]

        # Charger ou initialiser les données
        self.data = self.charger_ou_initialiser_donnees()
        self.prefill_row_index = None
        self._prefill_liq_id = None
        self._prefill_solid_material_id = None
        self._factor_original_values: dict = {}
        self._factor_editing_dirty: bool = False

        # data_materials transmis par MainWindow
        # data_materials doit contenir 'Materiau' et 'eCO2_kg'
        self.data_materials = self.load_material_df(data_materials)

        self.data_liquids = self.load_liquid_df()


        self.init_ui()
        self.afficher_donnees()

        if prefill_code or prefill_name:
            self.prefill_consumable(prefill_code or "", prefill_name or "", source=prefill_source)

        # Pré-remplit la source avec l'URL fournisseur si rien n'est déjà
        # renseigné côté source : pratique pour récupérer NACRES / prix sur la
        # page du fournisseur sans avoir à recopier l'URL à la main.
        prefill_url = (prefill_source_url or "").strip()
        if prefill_url and not self.source_input.text().strip():
            self.source_input.setText(prefill_url)

    def charger_ou_initialiser_donnees(self):
        if self._uses_sqlite():
            return self._load_sqlite_frame("data_masse", self.columns, include_sqlite_id=True)

        df = pd.DataFrame(columns=self.columns)
        data = self.migrate_source_signature_columns(df, mode="solid")
        for col in self.columns:
            if col not in data.columns:
                data[col] = ""
        return data.reindex(columns=self.columns)

    def sauvegarder_donnees(self, df=None):
        if df is None:
            df = self.data

        if self._uses_sqlite():
            self.data = self._load_sqlite_frame("data_masse", self.columns, include_sqlite_id=True)
            return

        data = self.migrate_source_signature_columns(df, mode="solid")
        for col in self.columns:
            if col not in data.columns:
                data[col] = ""
        self.data = data.reindex(columns=self.columns)
        return

    def _upsert_commercial_product(self, row_dict, existing_id=None):
        if not self._uses_sqlite():
            self.data = self.ajouter_objet_df(self.data, row_dict)
            return None
        product_id = upsert_commercial_product(
            self.sqlite_path,
            row_dict,
            existing_id=existing_id,
        )
        self.data = self._load_sqlite_frame("data_masse", self.columns, include_sqlite_id=True)
        return product_id

    def _current_dataframe_and_columns(self):
        mode = self.current_mode()
        if mode == self.MODE_LIQUID_FACTOR:
            return self.data_liquids, self.columns_liquids
        if mode == self.MODE_SOLID_FACTOR:
            return self.data_materials, self.columns_materials
        return self.data, self.columns

    def _normalise_import_columns(self, df):
        reverse_labels = {label: col for col, label in self.COLUMN_DISPLAY_LABELS.items()}
        renamed = df.rename(columns={col: reverse_labels.get(col, col) for col in df.columns})
        return renamed

    def _import_rows_from_dataframe(self, df):
        mode = self.current_mode()
        imported = 0
        if mode == self.MODE_SOLID_FACTOR:
            for _, row in df.iterrows():
                if str(row.get("Materiau", "")).strip():
                    upsert_material_factor(self.sqlite_path, row.to_dict())
                    imported += 1
            self.data_materials = self.load_material_df()
        elif mode == self.MODE_LIQUID_FACTOR:
            for _, row in df.iterrows():
                if str(row.get("Produit", "")).strip():
                    upsert_liquid_factor(self.sqlite_path, row.to_dict())
                    imported += 1
            self.data_liquids = self.load_liquid_df()
        else:
            for _, row in df.iterrows():
                if str(row.get("Consommable", "")).strip():
                    upsert_commercial_product(
                        self.sqlite_path,
                        row.to_dict(),
                        existing_id=self._sqlite_row_id(row),
                    )
                    imported += 1
            self.data = self._load_sqlite_frame("data_masse", self.columns, include_sqlite_id=True)
        return imported

    def _uses_sqlite(self):
        return bool(getattr(self, "sqlite_path", None))

    def _load_sqlite_frame(self, key, columns, include_sqlite_id=False):
        frames = load_legacy_dataframes(self.sqlite_path)
        df = frames[key].copy()
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        if include_sqlite_id and SQLITE_ID_COL not in df.columns:
            df[SQLITE_ID_COL] = ""
        ordered_columns = columns + ([SQLITE_ID_COL] if include_sqlite_id else [])
        return df.reindex(columns=ordered_columns)

    def _reload_sqlite_frames(self):
        self.data = self._load_sqlite_frame("data_masse", self.columns, include_sqlite_id=True)
        self.data_materials = self._load_sqlite_frame("data_materials", self.columns_materials)
        self.data_liquids = self._load_sqlite_frame("data_liquides", self.columns_liquids)

    @staticmethod
    def _sqlite_row_id(row):
        if row is None:
            return None
        try:
            value = row.get(SQLITE_ID_COL, "")
        except AttributeError:
            value = ""
        return clean_sqlite_id(value)

    @staticmethod
    def _clean_cell(value):
        if pd.isna(value):
            return ""
        text = str(value).strip()
        return "" if text.lower() in ("", "nan", "none", "n/a") else text

    @staticmethod
    def _looks_like_documentary_source(value):
        text = DataMassWindow._clean_cell(value)
        if not text:
            return False
        return bool(
            re.search(r"https?://|www\.|doi\s*:|doi\.org|10\.\d{4,9}/", text, flags=re.IGNORECASE)
        )

    @staticmethod
    def _looks_like_url(value):
        """Détecte si la valeur contient une URL ou un DOI ouvrable dans un navigateur."""
        text = (value or "").strip()
        if not text:
            return False
        return bool(
            re.search(r"https?://|www\.|doi\.org/|10\.\d{4,9}/", text, flags=re.IGNORECASE)
        )

    def _open_text_url(self, value):
        """Ouvre l'URL contenue dans `value` dans le navigateur par défaut."""
        text = (value or "").strip()
        if not text:
            return
        # Extrait la première URL explicite si le champ contient plus de texte.
        match = re.search(r"https?://\S+|www\.\S+|10\.\d{4,9}/\S+", text)
        if match:
            url = match.group(0)
        else:
            url = text
        if url.lower().startswith("www."):
            url = "https://" + url
        elif url.lower().startswith("10."):
            url = "https://doi.org/" + url
        QDesktopServices.openUrl(QUrl(url))

    def migrate_source_signature_columns(self, df, mode):
        """Convertit l'ancien champ mixte sans le réécrire dans les bases."""
        data = df.copy()
        if "Source" not in data.columns:
            data["Source"] = ""
        if "Signature" not in data.columns:
            data["Signature"] = ""

        legacy_col = "Source/Signature"
        if legacy_col in data.columns:
            legacy = data[legacy_col].fillna("").astype(str).str.strip()
            if mode == "liquid":
                source_empty = data["Source"].fillna("").astype(str).str.strip() == ""
                data.loc[source_empty, "Source"] = legacy[source_empty]
            else:
                signature_empty = data["Signature"].fillna("").astype(str).str.strip() == ""
                data.loc[signature_empty, "Signature"] = legacy[signature_empty]
            data = data.drop(columns=[legacy_col])

        if mode == "solid" and "Lien / Note / Remarque" in data.columns:
            source_empty = data["Source"].fillna("").astype(str).str.strip() == ""
            source_notes = data["Lien / Note / Remarque"].map(
                lambda value: value if self._looks_like_documentary_source(value) else ""
            )
            data.loc[source_empty, "Source"] = source_notes[source_empty]

        return data

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
        elif mode == "consumable":
            self.consumable_section_headers.append(header)
        elif mode == "liquid_product":
            self.liquid_product_section_headers.append(header)
        elif mode == "solid_factor":
            self.solid_factor_section_headers.append(header)
        elif mode == "liquid":
            self.liquid_section_headers.append(header)
        elif mode == "liquid_packaging":
            self.liquid_packaging_section_headers.append(header)
        elif mode == "emission_factor":
            self.emission_factor_section_headers.append(header)
        return header

    def current_mode(self):
        if not hasattr(self, "type_combo"):
            return self.MODE_SOLID_CONSUMABLE
        return self.type_combo.currentData() or self.MODE_SOLID_CONSUMABLE

    def is_consumable_mode(self):
        return self.current_mode() in {self.MODE_SOLID_CONSUMABLE, self.MODE_LIQUID_CONSUMABLE}

    def is_factor_mode(self):
        return self.current_mode() in {self.MODE_SOLID_FACTOR, self.MODE_LIQUID_FACTOR}

    def is_manual_liquid_factor_selected(self):
        return (
            self.current_mode() == self.MODE_LIQUID_CONSUMABLE
            and getattr(self, "liquid_factor_combo", None) is not None
            and self.liquid_factor_combo.currentData() == "__manual__"
        )

    def update_action_button_text(self):
        if not hasattr(self, "add_button"):
            return
        mode = self.current_mode()
        editing_factor = (
            (mode == self.MODE_LIQUID_FACTOR and bool(getattr(self, "_prefill_liq_id", None)))
            or (mode == self.MODE_SOLID_FACTOR and bool(getattr(self, "_prefill_solid_material_id", None)))
        )
        if editing_factor:
            self.add_button.setText("Enregistrer les modifications")
        elif self.prefill_row_index is not None or getattr(self, "_prefill_liq_produit", None):
            self.add_button.setText("Enregistrer les informations")
        else:
            labels = {
                self.MODE_SOLID_CONSUMABLE: "Ajouter le consommable solide",
                self.MODE_LIQUID_CONSUMABLE: "Ajouter le consommable liquide",
                self.MODE_SOLID_FACTOR: "Ajouter le facteur solide",
                self.MODE_LIQUID_FACTOR: "Ajouter le facteur liquide",
            }
            self.add_button.setText(labels.get(mode, "Ajouter l'objet"))
        self._update_add_button_color()
        self._update_factor_status_label()

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

    def create_helped_field(self, field, tooltip):
        row = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        info_button = QPushButton("i")
        info_button.setFixedWidth(28)
        info_button.setToolTip(tooltip)
        info_button.clicked.connect(
            lambda _checked=False, button=info_button:
                QToolTip.showText(QCursor.pos(), tooltip, button, button.rect(), 20000)
        )
        field.setToolTip(tooltip)
        layout.addWidget(field, 1)
        layout.addWidget(info_button)
        row.setLayout(layout)
        self.helped_field_widgets[field] = row
        return row

    def form_field_widget(self, widget):
        return self.helped_field_widgets.get(widget, widget)

    def init_ui(self):
        main_layout = QVBoxLayout()

        self.form_layout = QFormLayout()
        self.helped_field_widgets = {}
        self.required_fields = []
        self.solid_section_headers = []
        self.consumable_section_headers = []
        self.liquid_product_section_headers = []
        self.solid_factor_section_headers = []
        self.liquid_section_headers = []
        self.liquid_packaging_section_headers = []
        self.emission_factor_section_headers = []

        # Sélecteur de type
        self.add_section_header("Identification")
        self.type_combo = QComboBox()
        if self.mode_filter == "factor":
            options = [
                ("Facteur d'émission solide / matériau", self.MODE_SOLID_FACTOR),
                ("Facteur d'émission liquide / solvant", self.MODE_LIQUID_FACTOR),
            ]
        else:
            options = [
                ("Consommable solide", self.MODE_SOLID_CONSUMABLE),
                ("Consommable liquide", self.MODE_LIQUID_CONSUMABLE),
            ]
        for label, mode in options:
            self.type_combo.addItem(label, mode)
        self.type_combo.setStyleSheet("QComboBox { font-size: 13px; font-weight: 600; }")
        if self.initial_mode:
            idx = self.type_combo.findData(self.initial_mode)
            if idx != -1:
                self.type_combo.setCurrentIndex(idx)
        self.type_combo.currentIndexChanged.connect(self.on_type_changed)
        self.form_layout.addRow("Type d'objet :", self.type_combo)
        self.is_liquid = self.current_mode() == self.MODE_LIQUID_FACTOR

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
        mats_with_empty = [""] + mats

        # Second matériau (optionnel)
        self.masse2_input = QLineEdit()
        self.materiau2_combo = QComboBox()
        self.materiau2_combo.addItems(mats_with_empty)

        # Emballage
        self.masse_emb_input = QLineEdit()
        self.mat_emb_combo = QComboBox()
        self.mat_emb_combo.addItems(mats_with_empty)
        self.nbr_emb_input = QLineEdit()
        self.nbr_emb_input.setValidator(QIntValidator(1, 999999, self))
        self.nbr_emb_input.setPlaceholderText("Laissez vide si l'emballage est propre à 1 unité")

        # Conditionnement
        self.masse_cond_input = QLineEdit()
        self.mat_cond_combo = QComboBox()
        self.mat_cond_combo.addItems(mats_with_empty)
        self.nbr_cond_input = QLineEdit()
        self.nbr_cond_input.setValidator(QIntValidator(1, 999999, self))
        self.nbr_cond_input.setPlaceholderText("ex: 50 tubes par boîte, 1 bouteille par flacon")

        # Prix manuel
        self.price_mode_combo = QComboBox()
        self.price_mode_combo.addItems([self.PRICE_MODE_PACK, self.PRICE_MODE_UNIT])
        self.price_input = QLineEdit()
        self.price_input.setValidator(QDoubleValidator(0.0, 999999999.0, 6, self))
        self.price_input.setPlaceholderText("Prix obligatoire")
        self.price_preview_label = QLabel("Prix par unité vendue calculé : —")
        self.price_preview_label.setStyleSheet("color: #4b5563;")

        self.price_row_widget = QWidget()
        price_layout = QHBoxLayout()
        price_layout.setContentsMargins(0, 0, 0, 0)
        price_layout.addWidget(self.price_mode_combo, 2)
        price_layout.addWidget(self.price_input, 1)
        self.price_euro_label = QLabel("€")
        self.price_euro_label.setStyleSheet("font-weight: 600;")
        price_layout.addWidget(self.price_euro_label)
        self.price_row_widget.setLayout(price_layout)

        # Lien / Note
        self.lien_input = QLineEdit()

        # Instead of form_layout.addRow("Code NACRES:", self.nacres_input)
        self.nacres_combo = QComboBox()
        self.nacres_combo.setView(QListView())
        self.nacres_combo.setMaxVisibleItems(15)
        self.nacres_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
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
        self.materiau_combo.addItems(mats_with_empty)

        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Article, lien, DOI, documentation...")
        self.signature_input = QLineEdit()
        self.signature_input.setPlaceholderText("Nom, équipe, laboratoire...")

        # Champs facteur d'émission liquide/solvant ou matériau
        self.dens_input = QLineEdit()
        self.conc_input = QLineEdit()
        self.factor_input = QLineEdit()
        self.uncert_input = QLineEdit()
        self.vol_flacon_input = QLineEdit()
        self.vol_flacon_input.setPlaceholderText("ex: 1000 (mL) — optionnel")

        self.liquid_copy_factor_combo = QComboBox()
        self.liquid_copy_factor_combo.addItem("Nouveau facteur", None)
        if hasattr(self, "data_liquids") and self.data_liquids is not None and not self.data_liquids.empty:
            for _, row in self.data_liquids.iterrows():
                name = str(row.get("Produit", "") or "").strip()
                code = str(row.get("Code NACRES", "") or "").strip()[:4]
                if name:
                    self.liquid_copy_factor_combo.addItem(f"{name} ({code})", row.to_dict())
        self.liquid_copy_factor_combo.currentIndexChanged.connect(self.on_liquid_factor_template_selected)

        self.materiau_row_widget = self.create_material_selector(self.materiau_combo)
        self.materiau2_row_widget = self.create_material_selector(self.materiau2_combo)
        self.mat_emb_row_widget = self.create_material_selector(self.mat_emb_combo)
        self.mat_cond_row_widget = self.create_material_selector(self.mat_cond_combo)

        self.form_layout.addRow("Consommable:", self.nom_input)
        self.form_layout.addRow("Marque:", self.brand_input)
        self.form_layout.addRow("Référence:", self.ref_input)

        self.emission_factor_header = self.add_section_header(
            "Facteur d'émission du liquide / solvant",
            mode="emission_factor",
        )
        self.liquid_factor_combo = QComboBox()
        self.liquid_factor_combo.addItem("Utiliser un facteur existant...", "")
        self.liquid_factor_combo.addItem("Créer un nouveau facteur", "__manual__")
        if hasattr(self, "data_liquids") and self.data_liquids is not None and not self.data_liquids.empty:
            for _, row in self.data_liquids.iterrows():
                name = str(row.get("Produit", "") or "").strip()
                code = str(row.get("Code NACRES", "") or "").strip()[:4]
                factor_id = str(row.get("factor_id", "") or "").strip()
                if name:
                    self.liquid_factor_combo.addItem(
                        f"{name} ({code})", {"factor_id": factor_id, "name": name}
                    )
        self.liquid_factor_combo.currentIndexChanged.connect(self.on_commercial_liquid_factor_selected)
        self.manual_liquid_factor_name_input = QLineEdit()
        self.manual_liquid_factor_name_input.setPlaceholderText("ex: Acétone, Éthanol, DMEM...")
        self.solid_liquid_volume_input = QLineEdit()
        self.solid_liquid_volume_input.setPlaceholderText("ex: 1000 pour 1 L par bouteille")
        self.solid_liquid_volume_widget = self.create_helped_field(
            self.solid_liquid_volume_input,
            "Volume contenu dans une unité commerciale du consommable liquide. "
            "Exemple : saisir 1000 pour 1 L par bouteille, même si le carton contient plusieurs bouteilles."
        )
        self.masse_cond_widget = self.create_helped_field(
            self.masse_cond_input,
            "Pour un solide : masse du conditionnement primaire complet, par exemple la boîte qui contient les unités. "
            "Elle sera divisée par le nombre d'unités vendues. Pour un liquide : masse du flacon vide."
        )
        self.masse_emb_widget = self.create_helped_field(
            self.masse_emb_input,
            "Masse totale de l'emballage secondaire (carton externe, film plastique, sachet, intercalaire). "
            "Si plusieurs unités partagent cet emballage, renseigner cette masse pour l'ensemble "
            "puis indiquer le nombre d'unités à côté. Laissez vide s'il n'y a pas d'emballage secondaire."
        )
        self.nbr_emb_widget = self.create_helped_field(
            self.nbr_emb_input,
            "Nombre d'unités du consommable qui partagent ce même emballage secondaire. "
            "Exemple : 50 si un sachet plastique regroupe 50 tubes. Laissez vide (≡ 1) si l'emballage "
            "n'enveloppe qu'une seule unité (sleeve individuel d'une pipette)."
        )
        self.form_layout.addRow("Copier un facteur existant :", self.liquid_copy_factor_combo)
        self.form_layout.addRow("Utiliser un facteur existant / créer un nouveau facteur :", self.liquid_factor_combo)
        self.form_layout.addRow("Nom du nouveau facteur :", self.manual_liquid_factor_name_input)
        self.form_layout.addRow("Densité (g/mL):", self.dens_input)
        self.form_layout.addRow("Concentration (mg/mL):", self.conc_input)
        self.form_layout.addRow("Facteur CO₂ (kg eCO₂/kg):", self.factor_input)
        self.form_layout.addRow("Incertitude (%) :", self.uncert_input)

        self.add_section_header("Matériau consommable 1", mode="solid")
        self.form_layout.addRow("Matériau consommable 1:", self.materiau_row_widget)
        self.form_layout.addRow("Masse matériau 1 (g):", self.masse_input)

        self.add_section_header("Matériau consommable 2 (optionnel)", mode="solid")
        self.form_layout.addRow("Matériau consommable 2:", self.materiau2_row_widget)
        self.form_layout.addRow("Masse matériau 2 (g):", self.masse2_input)

        self.add_section_header("Conditionnement vendu et prix", mode="consumable")
        self.form_layout.addRow("Unités par conditionnement vendu:", self.nbr_cond_input)
        self.form_layout.addRow("Volume vendu par unité de consommable (mL):", self.solid_liquid_volume_widget)
        self.form_layout.addRow("Matériau du conditionnement primaire:", self.mat_cond_row_widget)
        self.form_layout.addRow("Masse du conditionnement primaire complet (g):", self.masse_cond_widget)
        self.form_layout.addRow("Prix:", self.price_row_widget)
        self.form_layout.addRow("", self.price_preview_label)

        self.add_section_header("Emballage secondaire (si présent)", mode="consumable")
        self.form_layout.addRow("Matériau emballage secondaire:", self.mat_emb_row_widget)
        self.form_layout.addRow("Masse emballage secondaire (g):", self.masse_emb_widget)
        self.form_layout.addRow("Unités partageant l'emballage secondaire:", self.nbr_emb_widget)

        self.register_required_field(self.type_combo, "Type d'objet")
        self.register_required_field(self.nacres_widget, "Code NACRES", control=self.nacres_combo)
        self.register_required_field(self.nom_input, "Consommable")
        self.register_required_field(self.brand_input, "Marque")
        self.register_required_field(self.ref_input, "Référence")
        self.register_required_field(self.nbr_cond_input, "Unités par conditionnement vendu")
        self.register_required_field(self.price_row_widget, "Prix", control=self.price_input)
        self.register_required_field(self.liquid_factor_combo, "Facteur liquide/solvant")
        self.register_required_field(self.manual_liquid_factor_name_input, "Nom du nouveau facteur")
        self.register_required_field(self.solid_liquid_volume_input, "Volume vendu par unité")

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

        self.form_layout.addRow("Volume vendu par unité (mL) :", self.vol_flacon_input)

        self.add_section_header("Contenant et emballage secondaire (optionnel)", mode="liquid_packaging")
        self.form_layout.addRow("Matériau du contenant :", self.mat_contenant_liq_row)
        self.form_layout.addRow("Masse du contenant vide (g) :", self.masse_contenant_liq_input)
        self.form_layout.addRow("Matériau de l'emballage secondaire :", self.mat_emb_liq_row)
        self.form_layout.addRow("Masse de l'emballage secondaire (g) :", self.masse_emb_liq_input)

        self.register_required_field(self.dens_input, "Densité")
        self.register_required_field(self.factor_input, "Facteur CO₂")

        self.add_section_header("Source et notes")
        # Lien / Note / Remarque : QLineEdit + bouton qui ouvre le lien si valide.
        lien_row = QHBoxLayout()
        lien_row.setContentsMargins(0, 0, 0, 0)
        lien_row.addWidget(self.lien_input)
        self.btn_open_lien = QPushButton("Ouvrir ↗")
        self.btn_open_lien.setToolTip("Ouvre le lien dans le navigateur si le champ contient une URL.")
        self.btn_open_lien.setMaximumWidth(110)
        self.btn_open_lien.setEnabled(False)
        self.btn_open_lien.clicked.connect(lambda: self._open_text_url(self.lien_input.text()))
        self.lien_input.textChanged.connect(
            lambda t: self.btn_open_lien.setEnabled(self._looks_like_url(t))
        )
        lien_row.addWidget(self.btn_open_lien)
        lien_widget = QWidget()
        lien_widget.setLayout(lien_row)
        self.form_layout.addRow("Lien / Note / Remarque:", lien_widget)

        # Source (article/lien) : même traitement.
        source_row = QHBoxLayout()
        source_row.setContentsMargins(0, 0, 0, 0)
        source_row.addWidget(self.source_input)
        self.btn_open_source = QPushButton("Ouvrir ↗")
        self.btn_open_source.setToolTip("Ouvre la source dans le navigateur si le champ contient une URL.")
        self.btn_open_source.setMaximumWidth(110)
        self.btn_open_source.setEnabled(False)
        self.btn_open_source.clicked.connect(lambda: self._open_text_url(self.source_input.text()))
        self.source_input.textChanged.connect(
            lambda t: self.btn_open_source.setEnabled(self._looks_like_url(t))
        )
        source_row.addWidget(self.btn_open_source)
        source_widget = QWidget()
        source_widget.setLayout(source_row)
        self.form_layout.addRow("Source (article/lien):", source_widget)

        self.form_layout.addRow("Signature (nom/équipe/labo):", self.signature_input)
        self.register_required_field(self.source_input, "Source")
        self.register_required_field(self.signature_input, "Signature")

        # Masquer ces lignes initialement
        for w in (
            self.liquid_copy_factor_combo,
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

        action_bar = QHBoxLayout()
        self.add_button = QPushButton("Ajouter l'objet")
        self.add_button.clicked.connect(self.ajouter_objet_utilisateur)
        action_bar.addWidget(self.add_button, 1)
        self.new_factor_button = QPushButton("✕  Effacer la sélection")
        self.new_factor_button.setToolTip("Désélectionner le facteur et revenir à la saisie d'un nouveau facteur")
        self.new_factor_button.clicked.connect(self._clear_factor_form)
        self.new_factor_button.setVisible(False)
        action_bar.addWidget(self.new_factor_button)
        main_layout.addLayout(action_bar)

        export_import_layout = QHBoxLayout()
        self.export_button = QPushButton("⬆ Exporter la base de données")
        self.export_button.clicked.connect(self.export_database)
        self.import_button = QPushButton("⬇ Mise à jour de la base de données")
        self.import_button.clicked.connect(self.import_database)
        export_import_layout.addWidget(self.export_button)
        export_import_layout.addWidget(self.import_button)
        main_layout.addLayout(export_import_layout)

        self.factor_status_label = QLabel(
            "Sélectionnez un facteur dans le tableau ci-dessous pour le modifier, "
            "ou remplissez le formulaire pour en créer un nouveau."
        )
        self.factor_status_label.setWordWrap(True)
        self.factor_status_label.setStyleSheet("color: #6b7280; font-style: italic; padding: 4px 0;")
        self.factor_status_label.setVisible(False)
        main_layout.addWidget(self.factor_status_label)

        # Tableau des données
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels(self.display_column_labels(self.columns))
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
        self.update_action_button_text()
        self.table.itemSelectionChanged.connect(self._on_factor_table_row_selected)
        self.nacres_search.textChanged.connect(self.filter_nacres_list)
        self.nacres_combo.currentIndexChanged.connect(self.update_required_indicators)
        self.type_combo.currentIndexChanged.connect(self.update_required_indicators)
        self.price_mode_combo.currentIndexChanged.connect(self.update_price_preview)
        self.price_input.textChanged.connect(self.update_price_preview)
        self.nbr_cond_input.textChanged.connect(self.update_price_preview)
        for field in (
            self.nom_input, self.brand_input, self.ref_input,
            self.nbr_cond_input, self.price_input, self.source_input, self.signature_input,
            self.manual_liquid_factor_name_input, self.dens_input, self.factor_input,
            self.uncert_input
        ):
            field.textChanged.connect(self.update_required_indicators)
        for field in (
            self.nom_input, self.dens_input, self.conc_input,
            self.factor_input, self.uncert_input, self.lien_input,
            self.source_input, self.signature_input,
        ):
            field.textChanged.connect(self._on_factor_form_field_changed)
        self.load_nacres_list()
        self.update_required_indicators()
        self.update_price_preview()

    def on_type_changed(self, idx):
        """Bascule entre consommables et facteurs : met à jour visibilité + table."""
        mode = self.current_mode()
        self.is_liquid = mode == self.MODE_LIQUID_FACTOR
        if mode == self.MODE_LIQUID_FACTOR:
            self.data_liquids = self.load_liquid_df()
        elif mode == self.MODE_SOLID_FACTOR:
            self.data_materials = self.load_material_df(self.data_materials)
        self.update_form_visibility()             # masque/affiche les bons champs
        self.update_required_indicators()
        self.update_price_preview()
        self.afficher_donnees()                   # recharge la table avec le bon DF

    def load_nacres_list(self):
        if not self._uses_sqlite():
            self._all_nacres = []
            return

        try:
            with sqlite3.connect(self.sqlite_path) as conn:
                self._all_nacres = load_nacres_options(conn)
            self.filter_nacres_list()
        except Exception as e:
            self._all_nacres = []
            logger.exception("Impossible de charger la liste NACRES depuis SQLite : %s", e)

    def load_liquid_df(self):
        if self._uses_sqlite():
            return self._load_sqlite_frame("data_liquides", self.columns_liquids)

        df_liq = pd.DataFrame(columns=self.columns_liquids)
        df_liq = self.migrate_source_signature_columns(df_liq, mode="liquid")
        for col in self.columns_liquids:
            if col not in df_liq.columns:
                df_liq[col] = ""
        return df_liq.reindex(columns=self.columns_liquids)

    def load_material_df(self, initial_df=None):
        if self._uses_sqlite():
            return self._load_sqlite_frame("data_materials", self.columns_materials)

        if initial_df is not None:
            df_mat = initial_df.copy()
        else:
            df_mat = pd.DataFrame(columns=self.columns_materials)

        if "Source/Signature" in df_mat.columns:
            if "Source" not in df_mat.columns:
                df_mat["Source"] = ""
            if "Signature" not in df_mat.columns:
                df_mat["Signature"] = df_mat["Source/Signature"]
            df_mat = df_mat.drop(columns=["Source/Signature"])

        for col in self.columns_materials:
            if col not in df_mat.columns:
                df_mat[col] = ""
        return df_mat.reindex(columns=self.columns_materials)

    def save_material_factor(self, obj_dict):
        if self._uses_sqlite():
            try:
                upsert_material_factor(
                    self.sqlite_path,
                    obj_dict,
                    existing_id=self._prefill_solid_material_id,
                )
                self._prefill_solid_material_id = None
                self.data_materials = self.load_material_df()
                if self.current_mode() == self.MODE_SOLID_FACTOR:
                    self.afficher_donnees()
                return True
            except Exception as e:
                QMessageBox.warning(self, "Erreur", f"Impossible d'écrire le matériau dans SQLite : {e}")
                return False

        df_mat = self.load_material_df(self.data_materials)
        material_name = str(obj_dict.get("Materiau", "")).strip()
        mask = df_mat["Materiau"].astype(str).str.strip() == material_name
        if mask.any():
            idx = df_mat[mask].index[0]
            for col, val in obj_dict.items():
                if col not in df_mat.columns:
                    df_mat[col] = ""
                df_mat.at[idx, col] = val
        else:
            new_line = pd.DataFrame([obj_dict]).reindex(columns=self.columns_materials)
            df_mat = pd.concat([df_mat, new_line], ignore_index=True)

        df_mat = df_mat.reindex(columns=self.columns_materials)
        self.data_materials = df_mat
        if self.current_mode() == self.MODE_SOLID_FACTOR:
            self.afficher_donnees()
        return True

    def filter_nacres_list(self):
        search_text = self.nacres_search.text().strip().lower()
        self.nacres_combo.clear()
        self.nacres_combo.addItem("Sélectionnez un code NACRES...", None)
        for option in self._all_nacres:
            code = option.code
            desc = option.label
            if search_text in code.lower() or search_text in desc.lower():
                display_text = f"{code} - {desc}"
                self.nacres_combo.addItem(display_text, code)
                idx = self.nacres_combo.count() - 1
                if option.is_new_without_labo1point5_fe:
                    self.nacres_combo.setItemData(idx, _NACRES_NEW_NO_FE_COLOR, Qt.BackgroundRole)
                    self.nacres_combo.setItemData(idx, _NACRES_NEW_NO_FE_TOOLTIP, Qt.ToolTipRole)
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
        row_widget = self.form_field_widget(field_widget)
        label = self.form_layout.labelForField(row_widget)
        if label is None:
            return
        self.required_fields.append({
            "field": row_widget,
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
        mode = self.current_mode()
        is_consumable = self.is_consumable_mode()
        is_factor = self.is_factor_mode()
        manual_liquid_factor = self.is_manual_liquid_factor_selected()
        _label_alias = {
            (self.MODE_SOLID_FACTOR, "Consommable"): "Matériau",
            (self.MODE_LIQUID_FACTOR, "Consommable"): "Liquide / solvant",
        }
        for item in self.required_fields:
            field = item["field"]
            control = item["control"]
            label = item["label"]
            label_text = item["label_text"]
            display_text = _label_alias.get((mode, label_text), label_text)
            active = not field.isHidden()
            if is_factor and label_text in {"Marque", "Référence", "Code NACRES", "Unités par conditionnement vendu", "Prix"}:
                active = False
            if mode == self.MODE_SOLID_CONSUMABLE and label_text in {"Facteur liquide/solvant", "Nom du nouveau facteur", "Volume vendu par unité", "Densité", "Facteur CO₂"}:
                active = False
            if mode == self.MODE_LIQUID_CONSUMABLE and label_text in {"Nom du nouveau facteur", "Densité", "Facteur CO₂", "Source"} and not manual_liquid_factor:
                active = False
            if mode == self.MODE_LIQUID_CONSUMABLE and label_text == "Nom du nouveau facteur":
                active = manual_liquid_factor
            if mode == self.MODE_LIQUID_FACTOR and label_text in {"Marque", "Référence", "Code NACRES", "Unités par conditionnement vendu", "Prix", "Volume vendu par unité"}:
                active = False
            if mode == self.MODE_SOLID_FACTOR and label_text in {"Marque", "Référence", "Code NACRES", "Unités par conditionnement vendu", "Prix", "Facteur liquide/solvant", "Nom du nouveau facteur", "Volume vendu par unité", "Densité"}:
                active = False
            if is_consumable and label_text == "Source" and not manual_liquid_factor:
                active = False

            if not active:
                label.setText(f"{display_text}:")
                label.setStyleSheet("")
                control.setStyleSheet("")
                continue

            filled = self.is_required_field_filled(control)
            if filled:
                label.setText(f"✓ {display_text}:")
                label.setStyleSheet("color: #15803d; font-weight: 600;")
            else:
                label.setText(f"✗ {display_text}:")
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

        if self.price_mode_combo.currentText() == self.PRICE_MODE_UNIT:
            prix_conditionnement = price * nbr_cond
        else:
            prix_conditionnement = price

        return {"Prix du conditionnement": prix_conditionnement}

    def update_price_preview(self):
        if not self.is_consumable_mode():
            self.price_preview_label.setText("Prix par unité vendue calculé : /")
            self.price_preview_label.setStyleSheet("color: #4b5563;")
            return

        price_text = self.price_input.text().strip().replace(',', '.')
        nbr_text = self.nbr_cond_input.text().strip()
        if not price_text:
            self.price_preview_label.setText("Prix par unité vendue calculé : —")
            self.price_preview_label.setStyleSheet("color: #4b5563;")
            return

        try:
            price = float(price_text)
            nbr_cond = int(nbr_text)
            if price < 0 or nbr_cond <= 0:
                raise ValueError
        except ValueError:
            self.price_preview_label.setText("Prix par unité vendue calculé : valeur à vérifier")
            self.price_preview_label.setStyleSheet("color: #dc2626; font-weight: 600;")
            return

        if self.price_mode_combo.currentText() == self.PRICE_MODE_UNIT:
            prix_unitaire = price
            prix_conditionnement = price * nbr_cond
        else:
            prix_conditionnement = price
            prix_unitaire = price / nbr_cond

        self.price_preview_label.setText(
            f"Prix par unité vendue calculé : {prix_unitaire:.4g} € "
            f"| Prix du conditionnement vendu : {prix_conditionnement:.4g} €"
        )
        self.price_preview_label.setStyleSheet("color: #15803d; font-weight: 600;")

    def _select_nacres_code(self, code_value):
        code4 = str(code_value or "").strip().upper()[:4]
        if not code4:
            return
        idx = self.nacres_combo.findData(code4)
        if idx == -1:
            for i in range(self.nacres_combo.count()):
                if self.nacres_combo.itemText(i).startswith(code4):
                    idx = i
                    break
        if idx != -1:
            self.nacres_combo.setCurrentIndex(idx)

    def _find_liquid_factor_row(self, factor_name):
        name = str(factor_name or "").strip()
        if not name or self.data_liquids is None or self.data_liquids.empty:
            return None
        rows = self.data_liquids[
            self.data_liquids["Produit"].astype(str).str.strip() == name
        ]
        return rows.iloc[0] if not rows.empty else None

    def on_commercial_liquid_factor_selected(self):
        """Prépare le formulaire produit commercial quand un facteur liquide est choisi."""
        if self.current_mode() != self.MODE_LIQUID_CONSUMABLE:
            return
        factor_name = self.liquid_factor_combo.currentData()
        self.update_form_visibility()
        if factor_name == "__manual__":
            return
        row = self._find_liquid_factor_row(factor_name)
        if row is None:
            return
        self._select_nacres_code(row.get("Code NACRES", ""))

    def on_liquid_factor_template_selected(self):
        """Copie un facteur existant dans les champs du référentiel liquide/solvant."""
        row = self.liquid_copy_factor_combo.currentData()
        if not isinstance(row, dict):
            return

        def _clean_value(value):
            if pd.isna(value):
                return ""
            text = str(value).strip()
            return "" if text.lower() in ("", "nan", "n/a", "none") else text

        self._select_nacres_code(row.get("Code NACRES", ""))

        for field, col in (
            (self.dens_input, "Densité (g/mL)"),
            (self.conc_input, "Concentration (mg/mL)"),
            (self.factor_input, "Facteur CO₂ (kg CO₂e/kg)"),
            (self.uncert_input, "Incertitude (%)"),
            (self.lien_input, "Note"),
        ):
            value = _clean_value(row.get(col, ""))
            if value:
                field.setText(value)
        source = _clean_value(row.get("Source", "")) or _clean_value(row.get("Source/Signature", ""))
        if source:
            self.source_input.setText(source)

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
        mode = self.current_mode()
        is_solid_consumable = mode == self.MODE_SOLID_CONSUMABLE
        is_liquid_consumable = mode == self.MODE_LIQUID_CONSUMABLE
        is_solid_factor = mode == self.MODE_SOLID_FACTOR
        is_liq = mode == self.MODE_LIQUID_FACTOR
        is_consumable = is_solid_consumable or is_liquid_consumable
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
        nbr_emb      = self.nbr_emb_input.text().strip()
        masse_cond_str = self.masse_cond_input.text().strip().replace(',', '.')
        mat_cond     = self.mat_cond_combo.currentText()
        nbr_cond     = self.nbr_cond_input.text().strip()
        price_text   = self.price_input.text().strip()
        liquid_factor_source = ""
        liquid_factor_id = ""
        liquid_volume = ""
        manual_liquid_factor = self.is_manual_liquid_factor_selected()
        manual_liquid_factor_name = self.manual_liquid_factor_name_input.text().strip()
        if is_liquid_consumable:
            combo_data = self.liquid_factor_combo.currentData()
            if isinstance(combo_data, dict):
                liquid_factor_source = combo_data.get("name", "") or ""
                liquid_factor_id = combo_data.get("factor_id", "") or ""
            else:
                liquid_factor_source = combo_data or ""
            liquid_volume = self.solid_liquid_volume_input.text().strip().replace(',', '.')
        lien_note    = self.lien_input.text().strip()
        source = self.source_input.text().strip()
        signature = self.signature_input.text().strip()
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
        elif is_solid_factor:
            dens = conc = ""
            facteur = self.factor_input.text().strip().replace(',', '.')
            incert = self.uncert_input.text().strip().replace(',', '.')
        elif manual_liquid_factor:
            conc = ""
            dens = self.dens_input.text().strip().replace(',', '.')
            facteur = self.factor_input.text().strip().replace(',', '.')
            incert = self.uncert_input.text().strip().replace(',', '.')
        else:
            dens = conc = facteur = incert = ""

        if is_liquid_consumable and not manual_liquid_factor and not liquid_factor_source:
            QMessageBox.warning(
                self,
                "Facteur liquide / solvant requis",
                "Pour un consommable liquide, choisissez un facteur d'émission existant "
                "ou sélectionnez « Créer un nouveau facteur » puis renseignez les données du facteur."
            )
            return
        if is_liquid_consumable and manual_liquid_factor:
            missing_manual_factor = [
                label for label, value in (
                    ("nom du nouveau facteur", manual_liquid_factor_name),
                    ("densité", dens),
                    ("facteur CO₂", facteur),
                    ("source", source),
                    ("signature", signature),
                )
                if not value
            ]
            if missing_manual_factor:
                QMessageBox.warning(
                    self,
                    "Nouveau facteur incomplet",
                    "Pour créer un facteur liquide / solvant, renseignez : "
                    + ", ".join(missing_manual_factor)
                    + "."
                )
                return

        if is_liq:
            required_ok = all([nom, dens, facteur, source, signature])
        elif is_solid_factor:
            required_ok = all([nom, facteur, source, signature])
        elif manual_liquid_factor:
            required_ok = all([nom, marque, reference, nacres, nbr_cond, price_text, liquid_volume, manual_liquid_factor_name, dens, facteur, source, signature])
        elif is_liquid_consumable:
            required_ok = all([nom, marque, reference, nacres, nbr_cond, price_text, liquid_factor_source, liquid_volume, signature])
        else:
            required_ok = all([nom, marque, reference, nacres, nbr_cond, price_text, signature])
        if not required_ok:
            QMessageBox.warning(self, "Erreur", "Tous les champs obligatoires doivent être remplis.")
            return

        nbr_cond_value = None
        nbr_emb_value = None
        if is_consumable:
            try:
                nbr_cond_value = int(nbr_cond)
                if nbr_cond_value <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Erreur",
                    "Le nombre d'unités par conditionnement vendu doit être un entier positif."
                )
                return

            if nbr_emb:
                try:
                    nbr_emb_value = int(nbr_emb)
                    if nbr_emb_value <= 0:
                        raise ValueError
                except ValueError:
                    QMessageBox.warning(
                        self,
                        "Erreur",
                        "Le nombre d'unités partageant l'emballage secondaire doit être un entier positif "
                        "(laissez vide si l'emballage est propre à une seule unité)."
                    )
                    return

            try:
                if is_solid_consumable:
                    masse_str = self._parse_optional_float(masse_str, "La masse unitaire")
                    masse2_str = self._parse_optional_float(masse2_str, "La masse unitaire 2")
                else:
                    masse_str = ""
                    masse2_str = ""
                masse_emb_str = self._parse_optional_float(masse_emb_str, "La masse de l'emballage secondaire")
                masse_cond_str = self._parse_optional_float(masse_cond_str, "La masse du conditionnement primaire complet ou du contenant vide")
                if is_liquid_consumable:
                    liquid_volume = self._parse_optional_float(
                        liquid_volume,
                        "Le volume vendu par unité de consommable liquide"
                    )
                price_fields = self.compute_manual_price_fields(nbr_cond_value)
            except ValueError as exc:
                QMessageBox.warning(self, "Erreur", str(exc))
                return

            if is_liquid_consumable and nbr_cond_value > 1:
                QMessageBox.information(
                    self,
                    "Volume par unité vendue",
                    "Le volume saisi doit correspondre à une seule bouteille ou un seul flacon, "
                    "pas au volume total du conditionnement vendu. Exemple : pour un pack de "
                    "6 bouteilles de 1 L, saisissez 6 unités par conditionnement vendu et 1000 mL."
                )
        else:
            price_fields = {}

        if is_solid_factor or is_liq or manual_liquid_factor:
            try:
                facteur = self._parse_optional_float(facteur, "Le facteur CO₂")
                incert = self._parse_optional_float(incert, "L'incertitude")
                if is_liq or manual_liquid_factor:
                    dens = self._parse_optional_float(dens, "La densité")
                    conc = self._parse_optional_float(conc, "La concentration")
            except ValueError as exc:
                QMessageBox.warning(self, "Erreur", str(exc))
                return

        if is_consumable:
            ignore_index = self.prefill_row_index
            erreur = self.verifier_existence_objet(nom, reference, nacres, ignore_index=ignore_index)
            if erreur:
                QMessageBox.warning(self, "Erreur", erreur)
                return

        was_update = (
            is_consumable
            and self.prefill_row_index is not None
            and self.prefill_row_index in self.data.index
        )

        if is_solid_factor:
            uncertainty_value = ""
            if incert != "":
                try:
                    raw_uncert = float(incert)
                    uncertainty_value = raw_uncert / 100.0 if raw_uncert > 1 else raw_uncert
                except ValueError:
                    uncertainty_value = incert
            nouvel_objet = {
                "Materiau": nom,
                "Equivalent CO₂ (kg eCO₂/kg)": facteur,
                "uncertainty": uncertainty_value,
                "Source": source,
                "Signature": signature,
            }
        elif is_liq:
            nouvel_objet = {
                "Produit": nom,
                "Type": "Liquide",
                "Code NACRES": "",
                "CAS": "",
                "Référence": "",
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
                "Source": source,
                "Signature": signature,
                "date d'ajout": date.today().isoformat(),
                "Note": lien_note
            }
        else:
            if manual_liquid_factor:
                manual_factor_row = {
                    "Produit": manual_liquid_factor_name,
                    "Type": "Liquide / solvant",
                    "Code NACRES": nacres,
                    "CAS": "",
                    "Référence": "",
                    "Unité": "mL",
                    "Densité (g/mL)": dens,
                    "Concentration (mg/mL)": "",
                    "Facteur CO₂ (kg CO₂e/kg)": facteur,
                    "Incertitude (%)": incert,
                    "Source": source,
                    "Signature": signature,
                    "date d'ajout": date.today().isoformat(),
                    "Note": lien_note,
                }
                saved_factor_id = self.save_liquid(manual_factor_row)
                if saved_factor_id is False:
                    return
                liquid_factor_source = manual_liquid_factor_name
                if saved_factor_id and saved_factor_id is not True:
                    liquid_factor_id = str(saved_factor_id)

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
                "Matériau consommable": materiau if is_solid_consumable else "",
                "Masse unitaire deuxieme materiaux (g)": masse2_str,
                "Matériau deuxieme materiaux": materiau2 if is_solid_consumable else "",
                "Masse unitaire troisième materiaux (g)": "",
                "Matériau troisième materiaux": "",
                "Masse emballage unitaire (g)": masse_emb_str,
                "Matériau emballage": mat_emb,
                "Nbr par emballage secondaire": nbr_emb_value,
                "Masse condionnement (g)": masse_cond_str,
                "Matériau conditionnement": mat_cond,
                "Nbr par conditionnement": nbr_cond_value,
                "Unité liquide": "mL" if is_liquid_consumable else "",
                "Volume flacon (mL)": liquid_volume,
                "Facteur liquide source": liquid_factor_source,
                "emission_factor_id": liquid_factor_id,
                "date d'ajout": date.today().isoformat(),
                "Lien / Note / Remarque": lien_note,
                "Source": source,
                "Signature": signature
            })

            if price_fields:
                nouvel_objet.update(price_fields)

        if is_solid_factor:
            if self.save_material_factor(nouvel_objet) is False:
                return
        elif is_liq:
            if self.save_liquid(nouvel_objet) is False:
                return
        else:
            if self._uses_sqlite():
                existing_id = None
                if self.prefill_row_index is not None and self.prefill_row_index in self.data.index:
                    existing_id = self._sqlite_row_id(self.data.loc[self.prefill_row_index])
                try:
                    self._upsert_commercial_product(nouvel_objet, existing_id=existing_id)
                except Exception as e:
                    QMessageBox.warning(self, "Erreur", f"Impossible d'écrire le consommable dans SQLite : {e}")
                    return
            elif self.prefill_row_index is not None and self.prefill_row_index in self.data.index:
                for col in self.columns:
                    self.data.at[self.prefill_row_index, col] = nouvel_objet.get(col, "")
            else:
                self.data = self.ajouter_objet_df(self.data, nouvel_objet)
            if not self._uses_sqlite():
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
        self.nbr_emb_input.clear()
        self.masse_cond_input.clear()
        self.mat_cond_combo.setCurrentIndex(0)
        self.nbr_cond_input.clear()
        self.price_mode_combo.setCurrentIndex(0)
        self.price_input.clear()
        self.liquid_factor_combo.setCurrentIndex(0)
        self.liquid_copy_factor_combo.setCurrentIndex(0)
        self.manual_liquid_factor_name_input.clear()
        self.solid_liquid_volume_input.clear()
        self.lien_input.clear()
        self.source_input.clear()
        self.signature_input.clear()
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
        self._prefill_liq_produit = None
        self._prefill_liq_id = None
        self._prefill_solid_material_id = None
        self._factor_original_values = {}
        self._factor_editing_dirty = False
        if hasattr(self, "new_factor_button"):
            self.new_factor_button.setVisible(False)
        self.update_action_button_text()
        self.update_required_indicators()
        self.update_price_preview()

        action = "mis à jour" if was_update else "ajouté"
        QMessageBox.information(self, "Succès", f"L'objet '{nom}' a été {action} avec succès.")
        self.data_added.emit()
        self.afficher_donnees()

    def save_liquid(self, obj_dict):
        """Ajoute ou met à jour un facteur liquide."""
        if self._uses_sqlite():
            try:
                factor_uuid = upsert_liquid_factor(
                    self.sqlite_path,
                    obj_dict,
                    existing_id=self._prefill_liq_id,
                )
                self._prefill_liq_produit = None
                self._prefill_liq_id = None
                self.data_liquids = self.load_liquid_df()
                if self.current_mode() == self.MODE_LIQUID_FACTOR:
                    self.afficher_donnees()
                return factor_uuid
            except Exception as e:
                QMessageBox.warning(self, "Erreur", f"Impossible d'écrire le liquide dans SQLite : {e}")
                return False

        df_liq = self.load_liquid_df()
        target_name = getattr(self, '_prefill_liq_produit', None) or str(obj_dict.get("Produit", "")).strip()
        if target_name:
            mask = df_liq["Produit"].astype(str).str.strip() == target_name
            if mask.any():
                idx = df_liq[mask].index[0]
                for col, val in obj_dict.items():
                    if col not in df_liq.columns:
                        df_liq[col] = ""
                    df_liq.at[idx, col] = val
                self._prefill_liq_produit = None
                self.data_liquids = df_liq
                if self.current_mode() == self.MODE_LIQUID_FACTOR:
                    self.afficher_donnees()
                return True

        new_line = pd.DataFrame([obj_dict]).reindex(columns=self.columns_liquids)
        df_liq = pd.concat([df_liq, new_line], ignore_index=True)
        self.data_liquids = df_liq
        if self.current_mode() == self.MODE_LIQUID_FACTOR:
            self.afficher_donnees()
        return True

    def ajouter_objet_df(self, df, objet):
        nouvel_objet = pd.DataFrame([objet])
        nouvel_objet = nouvel_objet.reindex(columns=self.columns)

        if df.empty:
            return nouvel_objet
        else:
            return pd.concat([df, nouvel_objet], ignore_index=True)

    def display_column_labels(self, columns):
        return [self.COLUMN_DISPLAY_LABELS.get(col, col) for col in columns]

    def afficher_donnees(self):
        # Réinitialiser le tableau
        self.table.clearContents()
        mode = self.current_mode()
        if mode == self.MODE_LIQUID_FACTOR:
            df, cols = self.data_liquids, self.columns_liquids
        elif mode == self.MODE_SOLID_FACTOR:
            df, cols = self.data_materials, self.columns_materials
        else:
            df, cols = self.data, self.columns

        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(self.display_column_labels(cols))

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
        """Montre/masque les champs en fonction du type d'objet."""
        mode = self.current_mode()
        is_solid_consumable = mode == self.MODE_SOLID_CONSUMABLE
        is_liquid_consumable = mode == self.MODE_LIQUID_CONSUMABLE
        is_solid_factor = mode == self.MODE_SOLID_FACTOR
        is_liquid_factor = mode == self.MODE_LIQUID_FACTOR
        is_consumable = is_solid_consumable or is_liquid_consumable
        manual_liquid_factor = self.is_manual_liquid_factor_selected()

        for header in self.solid_section_headers:
            header.setVisible(is_solid_consumable)
        for header in self.consumable_section_headers:
            header.setVisible(is_consumable)
        for header in self.liquid_product_section_headers:
            header.setVisible(is_liquid_consumable)
        for header in self.solid_factor_section_headers:
            header.setVisible(is_solid_factor)
        for header in self.liquid_section_headers:
            header.setVisible(is_liquid_factor)
        for header in self.liquid_packaging_section_headers:
            header.setVisible(False)
        for header in self.emission_factor_section_headers:
            header.setVisible(is_liquid_consumable or is_solid_factor or is_liquid_factor)
            if header is getattr(self, "emission_factor_header", None):
                if is_solid_factor:
                    header.setText("Facteur d'émission du matériau")
                else:
                    header.setText("Facteur d'émission du liquide / solvant")

        def set_visible(widget, visible):
            row_widget = self.form_field_widget(widget)
            lab = self.form_layout.labelForField(row_widget)
            if lab:
                lab.setVisible(visible)
            row_widget.setVisible(visible)

        def set_label(widget, text):
            lab = self.form_layout.labelForField(self.form_field_widget(widget))
            if lab:
                lab.setText(text)

        if is_solid_factor:
            set_label(self.nom_input, "Matériau:")
        elif is_liquid_factor:
            set_label(self.nom_input, "Liquide / solvant:")
        else:
            set_label(self.nom_input, "Consommable:")

        set_visible(self.brand_input, is_consumable)
        set_visible(self.ref_input, is_consumable)
        set_visible(self.nacres_widget, is_consumable)

        # Champs propres aux solides
        for w in (
            self.masse_input, self.materiau_row_widget,
            self.masse2_input, self.materiau2_row_widget,
        ):
            set_visible(w, is_solid_consumable)

        for w in (
            self.masse_emb_input, self.mat_emb_row_widget, self.nbr_emb_input,
            self.masse_cond_input, self.mat_cond_row_widget,
            self.nbr_cond_input, self.price_row_widget, self.price_preview_label,
        ):
            set_visible(w, is_consumable)

        set_label(
            self.mat_cond_row_widget,
            "Matériau du contenant/flacon:"
            if is_liquid_consumable else
            "Matériau du conditionnement primaire:"
        )
        set_label(
            self.masse_cond_input,
            "Masse du contenant/flacon vide (g):"
            if is_liquid_consumable else
            "Masse du conditionnement primaire complet (g):"
        )
        set_label(self.mat_emb_row_widget, "Matériau emballage secondaire:")
        set_label(self.masse_emb_input, "Masse emballage secondaire (g):")

        set_visible(self.liquid_factor_combo, is_liquid_consumable)
        set_visible(self.manual_liquid_factor_name_input, manual_liquid_factor)
        set_visible(self.solid_liquid_volume_input, is_liquid_consumable)

        # Champs propres aux facteurs
        set_visible(self.liquid_copy_factor_combo, is_liquid_factor)
        set_visible(self.dens_input, is_liquid_factor or manual_liquid_factor)
        set_visible(self.conc_input, is_liquid_factor)
        set_visible(self.factor_input, is_solid_factor or is_liquid_factor or manual_liquid_factor)
        set_visible(self.uncert_input, is_solid_factor or is_liquid_factor or manual_liquid_factor)
        set_label(self.factor_input, "Facteur CO₂ manuel (kg eCO₂/kg):" if manual_liquid_factor else "Facteur CO₂ (kg eCO₂/kg):")

        for w in (
            self.vol_flacon_input,
            self.mat_contenant_liq_row, self.masse_contenant_liq_input,
            self.mat_emb_liq_row, self.masse_emb_liq_input,
        ):
            set_visible(w, False)

        self.is_liquid = is_liquid_factor
        if hasattr(self, "new_factor_button"):
            _editing = (
                bool(getattr(self, "_prefill_liq_id", None))
                or bool(getattr(self, "_prefill_solid_material_id", None))
            )
            self.new_factor_button.setVisible((is_solid_factor or is_liquid_factor) and _editing)
        if hasattr(self, "factor_status_label"):
            self.factor_status_label.setVisible(is_solid_factor or is_liquid_factor)
        self.update_action_button_text()
        self.update_required_indicators()
        self.update_price_preview()

    def export_database(self):
        """
        Exporte la table affichée vers un CSV réimportable.
        """
        df, _cols = self._current_dataframe_and_columns()
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Exporter la base de données",
            "base_labeco2.csv",
            "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            df.to_csv(path, index=False, encoding="utf-8")
            QMessageBox.information(
                self, "Export réussi",
                f"{len(df)} ligne(s) exportée(s) vers :\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur export", f"Impossible d'exporter :\n{e}")

    def import_database(self):
        """
        Importe un CSV dans la base SQLite en respectant le mode affiché.
        """
        if not self._uses_sqlite():
            QMessageBox.warning(self, "SQLite requis", "L'import nécessite une base SQLite active.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Charger une mise à jour de la base de données",
            "",
            "CSV (*.csv)"
        )
        if not path:
            return

        try:
            new_df = pd.read_csv(path)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de lire le fichier :\n{e}")
            return
        new_df = self._normalise_import_columns(new_df)
        new_df = self.migrate_source_signature_columns(new_df, mode="solid")

        mode = self.current_mode()
        required_by_mode = {
            self.MODE_SOLID_FACTOR: "Materiau",
            self.MODE_LIQUID_FACTOR: "Produit",
            self.MODE_SOLID_CONSUMABLE: "Consommable",
            self.MODE_LIQUID_CONSUMABLE: "Consommable",
        }
        required_col = required_by_mode.get(mode, "Consommable")
        if required_col not in new_df.columns:
            QMessageBox.warning(
                self, "Format invalide",
                f"Le CSV doit contenir la colonne '{required_col}' pour le mode affiché."
            )
            return

        confirm = QMessageBox.question(
            self, "Confirmer la mise à jour",
            f"Importer {len(new_df)} ligne(s) dans la base SQLite active ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            imported = self._import_rows_from_dataframe(new_df)
            self.afficher_donnees()
            self.data_added.emit()

            QMessageBox.information(
                self, "Mise à jour réussie",
                f"{imported} ligne(s) importée(s) dans SQLite."
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de mettre à jour la base :\n{e}")

    # ------------------------------------------------------------------
    # Sélection dans le tableau → pré-remplissage du formulaire (facteurs)
    # ------------------------------------------------------------------

    def _on_factor_table_row_selected(self) -> None:
        """Appelé quand la sélection du tableau change. En mode facteur uniquement."""
        mode = self.current_mode()
        if mode not in (self.MODE_SOLID_FACTOR, self.MODE_LIQUID_FACTOR):
            return
        r = self.table.currentRow()
        if r < 0 or not self.table.selectedItems():
            return
        if mode == self.MODE_LIQUID_FACTOR:
            if r >= len(self.data_liquids):
                return
            self._prefill_form_from_liquid_row(self.data_liquids.iloc[r])
        else:
            if r >= len(self.data_materials):
                return
            self._prefill_form_from_material_row(self.data_materials.iloc[r])
        self.update_action_button_text()
        self.update_required_indicators()

    def _prefill_form_from_liquid_row(self, row) -> None:
        def _v(col):
            v = row.get(col, "")
            return "" if pd.isna(v) else str(v).strip()

        # Clear originals so dirty check returns False during fill
        self._factor_original_values = {}
        self._factor_editing_dirty = False

        self.nom_input.setText(_v("Produit"))
        dens = _v("Densité (g/mL)")
        if dens:
            self.dens_input.setText(dens)
        conc = _v("Concentration (mg/mL)")
        if conc:
            self.conc_input.setText(conc)
        co2 = _v("Facteur CO₂ (kg CO₂e/kg)")
        if co2:
            self.factor_input.setText(co2)
        uncert = _v("Incertitude (%)")  # déjà ×100 via l'adaptateur SQLite
        if uncert:
            self.uncert_input.setText(uncert)
        self.source_input.setText(_v("Source"))
        self.signature_input.setText(_v("Signature"))
        self.lien_input.setText(_v("Note"))

        self._prefill_liq_id = _v("factor_id") or None
        self._prefill_liq_produit = _v("Produit")

        # Snapshot values after fill so we can detect user edits
        self._factor_original_values = self._get_factor_field_values()
        self._factor_editing_dirty = False
        if hasattr(self, "new_factor_button"):
            self.new_factor_button.setVisible(bool(self._prefill_liq_id))

    def _prefill_form_from_material_row(self, row) -> None:
        def _v(col):
            v = row.get(col, "")
            return "" if pd.isna(v) else str(v).strip()

        # Clear originals so dirty check returns False during fill
        self._factor_original_values = {}
        self._factor_editing_dirty = False

        name = _v("Materiau")
        self.nom_input.setText(name)
        co2 = _v("Equivalent CO₂ (kg eCO₂/kg)")
        if co2:
            self.factor_input.setText(co2)
        raw_uncert = _v("uncertainty")
        if raw_uncert:
            try:
                self.uncert_input.setText(f"{float(raw_uncert) * 100:g}")
            except ValueError:
                pass
        self.source_input.setText(_v("Source"))
        self.signature_input.setText(_v("Signature"))

        self._prefill_solid_material_id = self._lookup_material_id_by_name(name)

        # Snapshot values after fill so we can detect user edits
        self._factor_original_values = self._get_factor_field_values()
        self._factor_editing_dirty = False
        if hasattr(self, "new_factor_button"):
            self.new_factor_button.setVisible(bool(self._prefill_solid_material_id))

    def _lookup_material_id_by_name(self, name: str) -> str | None:
        if not self._uses_sqlite() or not name:
            return None
        try:
            name_key = normalize_key(name)
            with sqlite3.connect(self.sqlite_path) as conn:
                row = conn.execute(
                    "SELECT id FROM materials WHERE name_key = ?"
                    " AND status != 'deprecated' LIMIT 1",
                    (name_key,),
                ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def _get_factor_field_values(self) -> dict:
        """Snapshot des champs du formulaire facteur pour détecter les modifications."""
        return {
            "nom": self.nom_input.text(),
            "dens": self.dens_input.text(),
            "conc": self.conc_input.text(),
            "factor": self.factor_input.text(),
            "uncert": self.uncert_input.text(),
            "source": self.source_input.text(),
            "signature": self.signature_input.text(),
            "lien": self.lien_input.text(),
        }

    def _check_factor_dirty(self) -> bool:
        if not self._factor_original_values:
            return False
        current = self._get_factor_field_values()
        return any(
            current.get(k, "").strip() != self._factor_original_values.get(k, "").strip()
            for k in self._factor_original_values
        )

    def _all_required_factor_fields_filled(self) -> bool:
        mode = self.current_mode()
        nom = self.nom_input.text().strip()
        facteur = self.factor_input.text().strip()
        source = self.source_input.text().strip()
        signature = self.signature_input.text().strip()
        if mode == self.MODE_LIQUID_FACTOR:
            dens = self.dens_input.text().strip()
            return all([nom, dens, facteur, source, signature])
        if mode == self.MODE_SOLID_FACTOR:
            return all([nom, facteur, source, signature])
        return False

    def _on_factor_form_field_changed(self) -> None:
        mode = self.current_mode()
        if mode not in (self.MODE_SOLID_FACTOR, self.MODE_LIQUID_FACTOR):
            return
        editing = (
            bool(getattr(self, "_prefill_liq_id", None))
            or bool(getattr(self, "_prefill_solid_material_id", None))
        )
        if editing:
            self._factor_editing_dirty = self._check_factor_dirty()
        self._update_add_button_color()
        self._update_factor_status_label()

    def _update_add_button_color(self) -> None:
        if not hasattr(self, "add_button"):
            return
        mode = self.current_mode()
        if mode not in (self.MODE_SOLID_FACTOR, self.MODE_LIQUID_FACTOR):
            self.add_button.setStyleSheet("")
            return
        editing = (
            bool(getattr(self, "_prefill_liq_id", None))
            or bool(getattr(self, "_prefill_solid_material_id", None))
        )
        if editing and self._factor_editing_dirty:
            self.add_button.setStyleSheet(
                "QPushButton { background-color: #dc2626; color: white; font-weight: 600;"
                " border-radius: 4px; padding: 6px 12px; }"
                "QPushButton:hover { background-color: #b91c1c; }"
            )
        elif self._all_required_factor_fields_filled():
            self.add_button.setStyleSheet(
                "QPushButton { background-color: #16a34a; color: white; font-weight: 600;"
                " border-radius: 4px; padding: 6px 12px; }"
                "QPushButton:hover { background-color: #15803d; }"
            )
        else:
            self.add_button.setStyleSheet("")

    def _update_factor_status_label(self) -> None:
        if not hasattr(self, "factor_status_label"):
            return
        mode = self.current_mode()
        if mode not in (self.MODE_SOLID_FACTOR, self.MODE_LIQUID_FACTOR):
            self.factor_status_label.setVisible(False)
            return
        self.factor_status_label.setVisible(True)
        editing_liq = bool(getattr(self, "_prefill_liq_id", None))
        editing_solid = bool(getattr(self, "_prefill_solid_material_id", None))
        if editing_liq or editing_solid:
            name = self.nom_input.text().strip()
            if self._factor_editing_dirty:
                self.factor_status_label.setText(
                    f"⚠ Modifications en attente pour « {name} » — pensez à enregistrer."
                )
                self.factor_status_label.setStyleSheet(
                    "color: #dc2626; font-style: italic; padding: 4px 0; font-weight: 600;"
                )
            else:
                self.factor_status_label.setText(
                    f"Facteur « {name} » sélectionné — modifiez les champs puis enregistrez."
                )
                self.factor_status_label.setStyleSheet(
                    "color: #15803d; font-style: italic; padding: 4px 0;"
                )
        else:
            self.factor_status_label.setText(
                "Sélectionnez un facteur dans le tableau ci-dessous pour le modifier, "
                "ou remplissez le formulaire pour en créer un nouveau."
            )
            self.factor_status_label.setStyleSheet("color: #6b7280; font-style: italic; padding: 4px 0;")

    def _clear_factor_form(self) -> None:
        """Efface le formulaire et repasse en mode 'nouveau facteur'."""
        self._prefill_liq_id = None
        self._prefill_liq_produit = None
        self._prefill_solid_material_id = None
        self._factor_original_values = {}
        self._factor_editing_dirty = False
        self.table.clearSelection()
        for field in (
            self.nom_input, self.dens_input, self.conc_input,
            self.factor_input, self.uncert_input, self.lien_input,
            self.source_input, self.signature_input,
        ):
            field.clear()
        if hasattr(self, "new_factor_button"):
            self.new_factor_button.setVisible(False)
        self.update_action_button_text()
        self.update_required_indicators()

    def prefill_consumable(self, code_nacres, consommable_name, source="solid"):
        """
        Pré-remplit le formulaire avec les données du consommable sélectionné
        dans la fenêtre principale.  Si une ligne existe déjà, tous les champs
        sont remplis (mode enrichissement). Gère solides et liquides.
        """
        self.prefill_row_index = None
        self._prefill_liq_produit = None
        self._prefill_liq_id = None
        self.update_action_button_text()

        def _clean_value(value):
            if pd.isna(value):
                return ""
            text = str(value).strip()
            return "" if text.lower() in ("", "nan", "n/a", "none") else text

        def _set_mode(mode):
            idx = self.type_combo.findData(mode)
            if idx != -1:
                self.type_combo.blockSignals(True)
                self.type_combo.setCurrentIndex(idx)
                self.type_combo.blockSignals(False)
                self.on_type_changed(idx)

        # ── NACRES : extraire le préfixe 4 chars ─────────────────────────────
        code4 = str(code_nacres).strip().upper()[:4]

        # ── Liquide ──────────────────────────────────────────────────────────
        if source == "liquid" and self.type_combo.findData(self.MODE_LIQUID_FACTOR) != -1:
            _set_mode(self.MODE_LIQUID_FACTOR)
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
                self._prefill_liq_id = clean_sqlite_id(row.get("factor_id", ""))
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
                _fill(self.source_input,             "Source")
                if not self.source_input.text().strip():
                    _fill(self.source_input,         "Source/Signature")
                _fill(self.signature_input,          "Signature")
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
        _set_mode(self.MODE_SOLID_CONSUMABLE)

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

        # ── Données existantes dans la base chargée ───────────────────────────
        mask = (
            (self.data["Code NACRES"].astype(str).str.strip().str.upper() == code4) &
            (self.data["Consommable"].astype(str).str.strip() == consommable_name.strip())
        )
        rows = self.data[mask]

        if not rows.empty:
            row = rows.iloc[0]
            is_liquid_product = looks_like_liquid_commercial_product(row)
            if is_liquid_product:
                _set_mode(self.MODE_LIQUID_CONSUMABLE)
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
            nbr_raw = row.get("Nbr par conditionnement", "")
            if not pd.isna(nbr_raw) and str(nbr_raw).strip() not in ("", "nan", "none"):
                try:
                    self.nbr_cond_input.setText(str(int(float(nbr_raw))))
                except (ValueError, TypeError):
                    self.nbr_cond_input.setText(str(nbr_raw).strip())
            nbr_emb_raw = row.get("Nbr par emballage secondaire", "")
            if not pd.isna(nbr_emb_raw) and str(nbr_emb_raw).strip() not in ("", "nan", "none", "1"):
                try:
                    self.nbr_emb_input.setText(str(int(float(nbr_emb_raw))))
                except (ValueError, TypeError):
                    self.nbr_emb_input.setText(str(nbr_emb_raw).strip())
            _fill(self.solid_liquid_volume_input, "Volume flacon (mL)")
            if not self.nbr_cond_input.text().strip():
                _fill(self.nbr_cond_input, "nb_unites_ijm")
            _fill(self.lien_input,      "Lien / Note / Remarque")
            _fill(self.source_input,    "Source")
            if not self.source_input.text().strip() and self._looks_like_documentary_source(row.get("Lien / Note / Remarque", "")):
                self.source_input.setText(_clean_value(row.get("Lien / Note / Remarque", "")))
            _fill(self.signature_input, "Signature")
            if not self.signature_input.text().strip():
                _fill(self.signature_input, "Source/Signature")

            prix_conditionnement = (
                _clean_value(row.get("Prix du conditionnement", ""))
                or _clean_value(row.get("prix_ht_ijm", ""))
            )
            prix_unitaire = _clean_value(row.get("prix_unitaire_ijm", ""))
            if prix_conditionnement:
                self.price_mode_combo.setCurrentText(self.PRICE_MODE_PACK)
                self.price_input.setText(prix_conditionnement)
            elif prix_unitaire:
                self.price_mode_combo.setCurrentText(self.PRICE_MODE_UNIT)
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

            factor_source = _clean_value(row.get("Facteur liquide source", ""))
            if factor_source:
                i = self.liquid_factor_combo.findData(factor_source)
                if i != -1:
                    self.liquid_factor_combo.setCurrentIndex(i)

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
            full_data = self.data
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
                    self.price_mode_combo.setCurrentText(self.PRICE_MODE_PACK)
                    self.price_input.setText(prix_conditionnement)
                elif prix_unitaire:
                    self.price_mode_combo.setCurrentText(self.PRICE_MODE_UNIT)
                    self.price_input.setText(prix_unitaire)

        self.update_required_indicators()
        self.update_price_preview()

    def calculer_eCO2_via_masse(self, consommable_name, quantite):
        """
        Calcule l'eCO2 total pour un consommable donné en additionnant :
          - matériau principal
          - deuxième matériau (si masse > 0)
          - emballage secondaire (divisé par Nbr par emballage secondaire si > 1)
          - conditionnement primaire (divisé par Nbr par conditionnement)

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

            # Cas conditionnement primaire : diviser par Nbr par conditionnement
            if col_masse == "Masse condionnement (g)":
                nb = last_obj.get("Nbr par conditionnement", 1)
                try:
                    nb = float(nb) if nb else 1
                    if nb > 0:
                        masse_g /= nb
                except (ValueError, TypeError):
                    pass
            # Cas emballage secondaire : diviser par Nbr par emballage secondaire si renseigné
            elif col_masse == "Masse emballage unitaire (g)":
                nb_emb = last_obj.get("Nbr par emballage secondaire", 1)
                try:
                    nb_emb = float(nb_emb) if nb_emb else 1
                    if nb_emb > 0:
                        masse_g /= nb_emb
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

    # ------------------------------------------------------------------
    # Pré-remplissage admin : édition d'un facteur d'émission existant
    # ------------------------------------------------------------------

    def prefill_factor_from_sqlite(self, factor_id: str) -> None:
        """Pré-remplit le formulaire depuis un facteur d'émission existant (admin)."""
        import sqlite3 as _sl

        try:
            conn = _sl.connect(self.sqlite_path)
            conn.row_factory = _sl.Row
            factor = conn.execute(
                """
                SELECT ef.*,
                       s.title AS _source_title,
                       c.name  AS _contributor_name
                FROM emission_factors ef
                LEFT JOIN sources      s ON s.id = ef.source_id
                LEFT JOIN contributors c ON c.id = ef.contributor_id
                WHERE ef.id = ?
                """,
                (factor_id,),
            ).fetchone()
            if factor is None:
                conn.close()
                return
            factor = dict(factor)

            material_id = None
            if factor.get("factor_type") == "material":
                row = conn.execute(
                    "SELECT id FROM materials WHERE emission_factor_id = ? LIMIT 1",
                    (factor_id,),
                ).fetchone()
                if row:
                    material_id = row[0]
            conn.close()
        except Exception:
            return

        def _set_mode(mode):
            idx = self.type_combo.findData(mode)
            if idx != -1:
                self.type_combo.blockSignals(True)
                self.type_combo.setCurrentIndex(idx)
                self.type_combo.blockSignals(False)
                self.on_type_changed(idx)

        def _fmt(v) -> str:
            if v is None:
                return ""
            try:
                f = float(v)
                return f"{f:g}"
            except (TypeError, ValueError):
                return str(v)

        source    = factor.get("_source_title", "") or ""
        signature = factor.get("_contributor_name", "") or ""
        co2       = factor.get("co2_factor")
        uncert    = factor.get("uncertainty")

        if factor.get("factor_type") == "liquid":
            _set_mode(self.MODE_LIQUID_FACTOR)
            self.update_form_visibility()
            self.afficher_donnees()

            self.nom_input.setText(factor.get("name", "") or "")
            if factor.get("density_g_ml") is not None:
                self.dens_input.setText(_fmt(factor["density_g_ml"]))
            if factor.get("concentration_mg_ml") is not None:
                self.conc_input.setText(_fmt(factor["concentration_mg_ml"]))
            if co2 is not None:
                self.factor_input.setText(_fmt(co2))
            if uncert is not None:
                self.uncert_input.setText(_fmt(uncert * 100))
            self.source_input.setText(source)
            self.signature_input.setText(signature)

            self._prefill_liq_id = factor_id
            self._prefill_liq_produit = factor.get("name", "")

        elif factor.get("factor_type") == "material":
            _set_mode(self.MODE_SOLID_FACTOR)
            self.update_form_visibility()
            self.afficher_donnees()

            self.nom_input.setText(factor.get("name", "") or "")
            if co2 is not None:
                self.factor_input.setText(_fmt(co2))
            if uncert is not None:
                self.uncert_input.setText(_fmt(uncert * 100))
            self.source_input.setText(source)
            self.signature_input.setText(signature)

            self._prefill_solid_material_id = material_id

        self.add_button.setText("Enregistrer les modifications")
        self.update_required_indicators()
