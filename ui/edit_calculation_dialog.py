# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# edit_calculation_dialog.py
import sys
import os
import pandas as pd
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, 
    QPushButton, QMessageBox, QWidget
)
from PySide6.QtCore import Qt
from ui.display_utils import (
    clean_text,
    format_subcategory_label,
    is_consumables_subcategory,
    normalize_nacres_prefix,
)

class EditCalculationDialog(QDialog):
    """
    Boîte de dialogue pour modifier un calcul existant.
    Cette classe reproduit la logique de sélection (catégorie, sous-catégorie, etc.)
    similaire à celle du MainWindow, mais pour l'édition.

    data (dict) est un dictionnaire contenant les infos du calcul à modifier.
    main_data : DataFrame principal (self.data du main_window) 
    data_masse : DataFrame pour les consommables (self.data_masse du main_window)
    data_materials : DataFrame pour les matériaux (self.data_materials du main_window)
    """

    def __init__(self, parent=None, data=None, main_data=None, data_masse=None,
                 data_materials=None, data_liquides=None):
        super().__init__(parent)
        self.setWindowTitle("Modifier le calcul")
        
        # Données existantes et référentiels
        self.data = data or {}
        self.main_data = main_data
        self.data_masse = data_masse
        self.data_materials = data_materials
        self.data_liquides = data_liquides if data_liquides is not None else pd.DataFrame()
        
        # Variables internes
        self.current_unit = None
        self.modified_data = None

        self.initUI()
        self.populate_fields(self.data)

    def initUI(self):
        """
        Initialise l'interface utilisateur de la fenêtre d'édition.
        Ajout de champs spécifiques pour les machines.
        """
        layout = QVBoxLayout(self)

        # --- 1) Label + Combo catégorie TOUJOURS visibles ---
        category_layout = QFormLayout()
        self.category_label = QLabel('Catégorie:')
        self.category_combo = QComboBox()

        # Remplir la combo avec vos catégories
        categories = self.main_data['category'].dropna().unique().tolist()
        # Retrait de 'Électricité' si nécessaire
        categories = [cat for cat in categories if cat != 'Électricité']
        categories.append('Machine')
        self.category_combo.addItems(sorted(categories))

        # Ajouter la ligne "Catégorie" tout en haut, dans le layout principal
        category_layout.addRow(self.category_label, self.category_combo)
        layout.addLayout(category_layout)

        # --- 2) Champs pour sous-catégories "normales" ---
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

        self.nacres_filtered_label = QLabel("Consommables :")
        self.nacres_filtered_label.setToolTip(
            "Matières premières, produits chimiques/biologiques et organismes vivants"
        )
        self.nacres_filtered_combo = QComboBox()
        self.nacres_filtered_label.setVisible(False)
        self.nacres_filtered_combo.setVisible(False)

        self.quantity_label = QLabel("Quantité:")
        self.quantity_input = QLineEdit()
        self.quantity_label.setVisible(False)
        self.quantity_input.setVisible(False)

        # Layout pour les catégories "normales"
        self.normal_form_layout = QFormLayout()
        # On ne met plus la catégorie ici (catégorie_label + combo) car on veut la garder toujours visible
        self.normal_form_layout.addRow(self.subcategory_label, self.subcategory_combo)
        self.normal_form_layout.addRow(self.search_label, self.search_field)
        self.normal_form_layout.addRow(self.subsub_name_label, self.subsub_name_combo)
        self.normal_form_layout.addRow(self.year_label, self.year_combo)
        self.normal_form_layout.addRow(self.input_label, self.input_field)
        self.normal_form_layout.addRow(self.days_label, self.days_field)
        self.normal_form_layout.addRow(self.nacres_filtered_label, self.nacres_filtered_combo)
        self.normal_form_layout.addRow(self.quantity_label, self.quantity_input)

        self.normal_widget = QWidget()
        self.normal_widget.setLayout(self.normal_form_layout)
        layout.addWidget(self.normal_widget)

        # --- 3) Champs spécifiques aux machines ---
        self.machine_name_label = QLabel('Nom de la machine:')
        self.machine_name_field = QLineEdit()
        self.power_label = QLabel('Puissance (kW):')
        self.power_field = QLineEdit()
        self.usage_time_label = QLabel("Temps d'utilisation/jour (h):")
        self.usage_time_field = QLineEdit()
        self.days_machine_label = QLabel("Nombre de jours d'utilisation:")
        self.days_machine_field = QLineEdit()
        self.electricity_label = QLabel("Type d'électricité:")
        self.electricity_combo = QComboBox()

        electricity_types = self.main_data[self.main_data['category'] == 'Électricité']['name'].dropna().unique()
        self.electricity_combo.addItems(sorted(electricity_types))

        self.machine_form_layout = QFormLayout()
        self.machine_form_layout.addRow(self.machine_name_label, self.machine_name_field)
        self.machine_form_layout.addRow(self.power_label, self.power_field)
        self.machine_form_layout.addRow(self.usage_time_label, self.usage_time_field)
        self.machine_form_layout.addRow(self.days_machine_label, self.days_machine_field)
        self.machine_form_layout.addRow(self.electricity_label, self.electricity_combo)

        self.machine_widget = QWidget()
        self.machine_widget.setLayout(self.machine_form_layout)
        layout.addWidget(self.machine_widget)

        # --- 4) Boutons Valider / Annuler ---
        buttons_layout = QHBoxLayout()
        self.validate_button = QPushButton("Valider")
        self.cancel_button = QPushButton("Annuler")
        buttons_layout.addWidget(self.validate_button)
        buttons_layout.addWidget(self.cancel_button)
        layout.addLayout(buttons_layout)

        # --- 5) Connexions signaux/slots ---
        # Comme avant (sauf qu'on ne déplace plus la catégorie)
        self.category_combo.currentIndexChanged.connect(self.update_subcategories)
        self.subcategory_combo.currentIndexChanged.connect(self.update_subsubcategory_names)
        self.search_field.textChanged.connect(self.update_subsubcategory_names)
        self.subsub_name_combo.currentIndexChanged.connect(self.update_years)
        self.year_combo.currentIndexChanged.connect(self.update_unit)
        self.year_combo.currentIndexChanged.connect(self.update_nacres_filtered_combo)
        self.nacres_filtered_combo.currentIndexChanged.connect(self.on_nacres_filtered_changed)

        self.validate_button.clicked.connect(self.on_validate)
        self.cancel_button.clicked.connect(self.reject)

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

    def _set_subcategory(self, subcategory):
        subcategory = clean_text(subcategory)
        index = self.subcategory_combo.findData(subcategory)
        if index < 0:
            display, _ = format_subcategory_label(subcategory)
            index = self.subcategory_combo.findText(display)
        if index >= 0:
            self.subcategory_combo.setCurrentIndex(index)

    def _add_consumable_item(self, code_nacres, consommable, source="solid"):
        code = clean_text(code_nacres)
        name = clean_text(consommable)
        if not code and not name:
            return
        self.nacres_filtered_combo.addItem(
            name or code,
            userData={"code_nacres": code, "consommable": name, "source": source}
        )
        index = self.nacres_filtered_combo.count() - 1
        tooltip = [f"Code NACRES : {code}"] if code else []
        if source == "liquid":
            tooltip.append("Consommable liquide")
        if tooltip:
            self.nacres_filtered_combo.setItemData(index, "\n".join(tooltip), Qt.ToolTipRole)

    def _selected_consumable_data(self):
        data = self.nacres_filtered_combo.currentData()
        if isinstance(data, dict):
            code = clean_text(data.get("code_nacres"))
            name = clean_text(data.get("consommable"))
            if code or name:
                return {
                    "code_nacres": code,
                    "consommable": name,
                    "source": clean_text(data.get("source")) or "solid",
                }
        text = clean_text(self.nacres_filtered_combo.currentText())
        if not text or text == "Aucune correspondance":
            return None
        if " - " in text:
            code, name = text.split(" - ", 1)
            return {"code_nacres": clean_text(code), "consommable": clean_text(name), "source": "solid"}
        return {"code_nacres": "", "consommable": text, "source": "solid"}

    def _select_consumable_item(self, code_nacres, consommable):
        code_prefix = normalize_nacres_prefix(code_nacres)
        name = clean_text(consommable)
        for index in range(self.nacres_filtered_combo.count()):
            data = self.nacres_filtered_combo.itemData(index)
            if not isinstance(data, dict):
                continue
            item_code = clean_text(data.get("code_nacres"))
            item_name = clean_text(data.get("consommable"))
            if item_name == name and normalize_nacres_prefix(item_code) == code_prefix:
                self.nacres_filtered_combo.setCurrentIndex(index)
                return True
        return False

    def _set_subsub_name(self, subsubcategory, name):
        code_prefix = normalize_nacres_prefix(subsubcategory)
        target = clean_text(f"{clean_text(subsubcategory)} - {clean_text(name)}").strip(" - ").casefold()
        fallback_index = -1
        for index in range(self.subsub_name_combo.count()):
            item_text = clean_text(self.subsub_name_combo.itemText(index))
            if item_text.casefold() == target:
                self.subsub_name_combo.setCurrentIndex(index)
                return
            if code_prefix and normalize_nacres_prefix(item_text) == code_prefix and fallback_index < 0:
                fallback_index = index
        if fallback_index >= 0:
            self.subsub_name_combo.setCurrentIndex(fallback_index)
        elif target:
            self.subsub_name_combo.setCurrentText(target)

    def _is_current_consumables(self):
        return (
            self.category_combo.currentText() == "Achats"
            and is_consumables_subcategory(self._current_subcategory())
        )

    def _update_year_visibility(self):
        show_year = self.year_combo.count() > 1 and not self._is_current_consumables()
        self.year_label.setVisible(show_year)
        self.year_combo.setVisible(show_year)

    def populate_fields(self, data):
        """
        Pré-remplit les champs avec les données du calcul existant 
        et autorise le changement de catégorie par la suite.
        """
        category = data.get('category', '')
        self.category_combo.setCurrentText(category)

        # Gère l’affichage machine vs normal
        self.update_subcategories()

        # --- Cas Machine ---
        if category == 'Machine':
            self.machine_name_field.setText(data.get('subcategory', ''))
            self.power_field.setText(str(data.get('power', '')))
            self.usage_time_field.setText(str(data.get('usage_time', '')))
            self.days_machine_field.setText(str(data.get('days_machine', '')))

            electricity_type = data.get('electricity_type', '')
            if electricity_type:
                self.electricity_combo.setCurrentText(electricity_type)

        else:
            # --- Cas Achats / Véhicules / Autres ---
            self._set_subcategory(data.get('subcategory', ''))
            self.update_subsubcategory_names()

            subsubcategory = data.get('subsubcategory', '')
            name = data.get('name', '')
            self._set_subsub_name(subsubcategory, name)

            self.update_years()
            self.year_combo.setCurrentText(str(data.get('year', '')))

            # Dans la plupart des catégories, "value" est ce qu'on affiche directement
            val = data.get('value', 0)
            self.input_field.setText(str(val))
            self.current_unit = data.get('unit', '')

            if self.current_unit:
                if category == 'Véhicules':
                    self.input_label.setText(f'Entrez la valeur journalière en {self.current_unit}:')
                elif self._is_current_consumables():
                    self.input_label.setText(f'Montant en {self.current_unit}:')
                else:
                    self.input_label.setText(f'Entrez la valeur en {self.current_unit}:')
                self.input_field.setEnabled(True)
            else:
                self.input_label.setText('Entrez la valeur:')
                self.input_field.setEnabled(False)

            # --- Spécifique Véhicules : on stocke un total dans 'value',
            #     mais on affiche du km/jour dans l’interface
            if category == 'Véhicules':
                # Rendre visible le champ "Nombre de jours"
                self.days_label.setVisible(True)
                self.days_field.setVisible(True)
                self.days_field.setEnabled(True)

                days = data.get('days', 1)
                self.days_field.setText(str(days))

                # val = km/jour (convention cohérente avec la saisie initiale)
                try:
                    km_per_day = float(val)
                except ValueError:
                    km_per_day = 0

                # On injecte km_per_day dans le champ input_field
                self.input_field.setText(str(km_per_day))

            else:
                self.days_label.setVisible(False)
                self.days_field.setVisible(False)
                self.days_field.setEnabled(False)

            # --- Cas Achats + Consommables => NACRES
            if category == 'Achats' and is_consumables_subcategory(data.get('subcategory', '')):
                self.update_nacres_filtered_combo()
                
                code_nacres = data.get('code_nacres', '')
                consommable = data.get('consommable', '')
                if code_nacres and consommable:
                    self._select_consumable_item(code_nacres, consommable)

                self.quantity_label.setVisible(True)
                self.quantity_input.setVisible(True)
                quantity = data.get('quantity', '')
                if quantity is not None:
                    self.quantity_input.setText(str(quantity))
            else:
                # Autres cas : masquer NACRES/quantité
                self.nacres_filtered_label.setVisible(False)
                self.nacres_filtered_combo.setVisible(False)
                self.nacres_filtered_combo.clear()
                self.quantity_label.setVisible(False)
                self.quantity_input.setVisible(False)
            self._update_year_visibility()

    def on_validate(self):
        try:
            category = self.category_combo.currentText()

            # --------------------------------------------------------------------------
            #  CAS "Machine"
            # --------------------------------------------------------------------------
            if category == 'Machine':
                machine_name = self.machine_name_field.text().strip()
                
                power_text = self.power_field.text().strip().replace(',', '.')
                usage_time_text = self.usage_time_field.text().strip().replace(',', '.')
                days_machine_text = self.days_machine_field.text().strip()

                if not power_text or not usage_time_text or not days_machine_text:
                    QMessageBox.warning(self, 'Erreur', 
                                        "Veuillez remplir tous les champs numériques de la machine.")
                    return

                try:
                    power = float(power_text)
                    usage_time = float(usage_time_text)
                    days_machine = int(days_machine_text)
                except ValueError:
                    QMessageBox.warning(self, 'Erreur', 
                                        "Veuillez entrer des valeurs numériques valides pour la machine.")
                    return

                electricity_type = self.electricity_combo.currentText()
                total_usage = power * usage_time * days_machine

                self.modified_data = {
                    'category': 'Machine',
                    'subcategory': machine_name,
                    'value': total_usage,
                    'unit': 'kWh',
                    'power': power,
                    'usage_time': usage_time,
                    'days_machine': days_machine,
                    'electricity_type': electricity_type,
                    'code_nacres': 'NA',
                    'consommable': 'NA',
                    'quantity': 0.0,
                }
                self.accept()
                return

            # --------------------------------------------------------------------------
            #  CAS Achats, Véhicules ou autres
            # --------------------------------------------------------------------------
            subcategory = self._current_subcategory()
            subsub_name = self.subsub_name_combo.currentText()
            subsubcategory, name = self.split_subsub_name(subsub_name)
            year = self.year_combo.currentText()

            # Lecture de la valeur depuis input_field
            input_text = self.input_field.text().strip().replace(',', '.')
            try:
                value_entered = float(input_text)
            except ValueError:
                QMessageBox.warning(self, 'Erreur', 'Veuillez entrer une valeur numérique valide.')
                return

            # Lecture sécurisée du nombre de jours
            days = 1
            if self.days_field.isVisible():
                days_text = self.days_field.text().strip()
                if days_text:
                    try:
                        days = int(days_text)
                    except ValueError:
                        QMessageBox.warning(self, 'Erreur', 
                                            'Veuillez entrer un nombre de jours valide.')
                        return

            # Pour tous les cas, value est km/jour (Véhicules) ou la valeur directe
            final_value = value_entered

            # Assemblage initial des données modifiées
            self.modified_data = {
                'category': category,
                'subcategory': subcategory,
                'subsubcategory': subsubcategory,
                'name': name,
                'year': year,
                'unit': self.current_unit,
                'value': final_value,   # km/jour pour Véhicules, valeur directe sinon
                'days': days,
                'code_nacres': 'NA',    # valeurs par défaut qui peuvent être modifiées plus loin
                'consommable': 'NA',
            }

            # Gestion du champ "Nombre de jours" pour Véhicules déjà prise en compte ci-dessus.

            # --- Gestion NACRES pour Achats de Consommables ---
            if category == 'Achats' and is_consumables_subcategory(subcategory):
                code_nacres = 'NA'
                consommable = 'NA'
                # Si on a un soussubcategory, en prendre les 4 premiers caractères pour NACRES de base
                if subsubcategory:
                    code_nacres = subsubcategory[:4]
                if self.nacres_filtered_combo.isVisible():
                    selected = self._selected_consumable_data()
                    if selected:
                        code_nacres = selected["code_nacres"] or code_nacres
                        consommable = selected["consommable"] or "NA"
                    else:
                        if subsubcategory:
                            code_nacres = subsubcategory[:4]
                        else:
                            code_nacres = 'NA'
                        consommable = 'NA'
                self.modified_data.update({
                    'code_nacres': code_nacres,
                    'consommable': consommable,
                })

                # Lecture sécurisée de la quantité
                if self.quantity_input.isVisible():
                    q_str = self.quantity_input.text().strip()
                    if not q_str:
                        QMessageBox.warning(self, 'Erreur', 
                                            "Le champ quantité est vide, veuillez saisir une quantité.")
                        return
                    try:
                        quantity_val = float(q_str.replace(',', '.'))
                        if quantity_val <= 0:
                            raise ValueError
                        self.modified_data['quantity'] = quantity_val
                    except ValueError:
                        QMessageBox.warning(self, 'Erreur', 
                                            'Veuillez entrer une quantité positive.')
                        return

            self.accept()

        except ValueError as ve:
            print("Erreur de conversion détectée :", ve)
            QMessageBox.warning(self, 'Erreur', f"Erreur de conversion numérique : {ve}")
            return

    def split_subsub_name(self, subsub_name):
        if ' - ' in subsub_name:
            subsubcategory, name = subsub_name.split(' - ', 1)
        else:
            subsubcategory = ''
            name = subsub_name
        return subsubcategory.strip(), name.strip()

    def update_subcategories(self):
        category = self.category_combo.currentText()
        if category == 'Machine':
            # Cacher le widget normal, afficher le widget machine
            self.normal_widget.setVisible(False)
            self.machine_widget.setVisible(True)
        else:
            # Afficher le widget normal, cacher le widget machine
            self.normal_widget.setVisible(True)
            self.machine_widget.setVisible(False)
            
            # Charger les sous-catégories
            subcategories = self.main_data[self.main_data['category'] == category]['subcategory'].dropna().unique()
            self._populate_subcategory_combo(subcategories.astype(str))

            self.update_subsubcategory_names()

            # Gérer la visibilité du champ "Nombre de jours" si Véhicules
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
        subcategory = self._current_subcategory()
        search_text = self.search_field.text().lower()
        mask = (self.main_data['category'] == category) & (self.main_data['subcategory'] == subcategory)
        filtered_data = self.main_data[mask]
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
        subcategory = self._current_subcategory()
        subsub_name = self.subsub_name_combo.currentText()
        subsubcategory, name = self.split_subsub_name(subsub_name)

        mask = (
            (self.main_data['category'] == category) &
            (self.main_data['subcategory'] == subcategory) &
            (self.main_data['subsubcategory'].fillna('') == subsubcategory) &
            (self.main_data['name'].fillna('') == name)
        )
        years = self.main_data[mask]['year'].dropna().astype(str).unique()
        self.year_combo.clear()
        self.year_combo.addItems(sorted(years))
        self._update_year_visibility()
        self.update_unit()

    def update_unit(self):
        category = self.category_combo.currentText()
        subcategory = self._current_subcategory()
        subsub_name = self.subsub_name_combo.currentText()
        year = self.year_combo.currentText()
        subsubcategory, name = self.split_subsub_name(subsub_name)

        mask = (
            (self.main_data['category'] == category) &
            (self.main_data['subcategory'] == subcategory) &
            (self.main_data['subsubcategory'].fillna('') == subsubcategory) &
            (self.main_data['name'].fillna('') == name) &
            (self.main_data['year'].astype(str) == year)
        )

        filtered_data = self.main_data[mask]
        if not filtered_data.empty:
            unit = filtered_data['unit'].values[0] or 'valeur'
            self.current_unit = unit
            if category == "Véhicules":
                self.input_label.setText(f'Entrez la valeur journalière en {unit}:')
            elif self._is_current_consumables():
                self.input_label.setText(f'Montant en {unit}:')
            else:
                self.input_label.setText(f'Entrez la valeur en {unit}:')
            self.input_field.setEnabled(True)
        else:
            self.current_unit = None
            if category == "Véhicules":
                self.input_label.setText('Entrez la valeur journalière:')
            else:
                self.input_label.setText('Entrez la valeur:')
            self.input_field.setEnabled(False)

    def update_nacres_filtered_combo(self):
        category = self.category_combo.currentText()
        subcategory = self._current_subcategory()
        subsub_name = self.subsub_name_combo.currentText()

        if category == 'Achats' and is_consumables_subcategory(subcategory):
            self.nacres_filtered_label.setVisible(True)
            self.nacres_filtered_combo.setVisible(True)
            self.nacres_filtered_combo.blockSignals(True)
            self.nacres_filtered_combo.clear()

            if subsub_name:
                subsubcategory, name = self.split_subsub_name(subsub_name)
                code_nacres_prefix = normalize_nacres_prefix(subsubcategory)
                filtered_entries = self.data_masse[
                    self.data_masse['Code NACRES'].astype(str).str.strip().str[:4].str.upper() == code_nacres_prefix
                ]

                if not filtered_entries.empty:
                    entries = []
                    for _, row in filtered_entries.iterrows():
                        nom_objet_val = clean_text(row.get("Consommable", ""))
                        code_val = clean_text(row.get("Code NACRES", ""))
                        if nom_objet_val:
                            entries.append((nom_objet_val.casefold(), code_val, nom_objet_val, "solid"))
                    for _, code, name, source in sorted(entries):
                        self._add_consumable_item(code, name, source)

                if self.data_liquides is not None and not self.data_liquides.empty:
                    liquid_entries = []
                    for _, row in self.data_liquides.iterrows():
                        code_val = clean_text(row.get("Code NACRES", ""))
                        produit = clean_text(row.get("Produit", ""))
                        if produit and normalize_nacres_prefix(code_val) == code_nacres_prefix:
                            liquid_entries.append((produit.casefold(), code_val, produit, "liquid"))
                    for _, code, name, source in sorted(liquid_entries):
                        self._add_consumable_item(code, name, source)

            # Toujours ajouter "Aucune correspondance"
            self.nacres_filtered_combo.addItem("Aucune correspondance", userData=None)
            self.nacres_filtered_combo.blockSignals(False)
            self.nacres_filtered_combo.setCurrentText("Aucune correspondance")

        else:
            self.nacres_filtered_label.setVisible(False)
            self.nacres_filtered_combo.setVisible(False)
            self.nacres_filtered_combo.clear()
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)

    def on_nacres_filtered_changed(self):
        selected = self._selected_consumable_data()
        if not selected:
            self.quantity_label.setVisible(False)
            self.quantity_input.setVisible(False)
        else:
            self.quantity_label.setVisible(True)
            self.quantity_input.setVisible(True)

            code_prefix = normalize_nacres_prefix(selected["code_nacres"])
            if code_prefix:
                for index in range(self.subsub_name_combo.count()):
                    if normalize_nacres_prefix(self.subsub_name_combo.itemText(index)) == code_prefix:
                        self.subsub_name_combo.setCurrentIndex(index)
                        break
