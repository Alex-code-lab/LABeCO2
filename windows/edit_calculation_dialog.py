# edit_calculation_dialog.py

import sys
import os
import pandas as pd
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, 
    QPushButton, QMessageBox, QWidget
)
from PySide6.QtCore import Qt

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

    def __init__(self, parent=None, data=None, main_data=None, data_masse=None, data_materials=None):
        super().__init__(parent)
        self.setWindowTitle("Modifier le calcul")
        
        # Données existantes et référentiels
        self.data = data or {}
        self.main_data = main_data
        self.data_masse = data_masse
        self.data_materials = data_materials
        
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

        # Champs pour catégories classiques
        self.category_label = QLabel('Catégorie:')
        self.category_combo = QComboBox()

        categories = self.main_data['category'].dropna().unique().tolist()
        # Retrait de 'Électricité' si nécessaire, comme dans main_window
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

        self.nacres_filtered_label = QLabel("Code NACRES Filtré :")
        self.nacres_filtered_combo = QComboBox()
        self.nacres_filtered_label.setVisible(False)
        self.nacres_filtered_combo.setVisible(False)

        self.quantity_label = QLabel("Quantité:")
        self.quantity_input = QLineEdit()
        self.quantity_label.setVisible(False)
        self.quantity_input.setVisible(False)

        # Champs spécifiques aux machines
        self.machine_name_label = QLabel('Nom de la machine:')
        self.machine_name_field = QLineEdit()
        self.power_label = QLabel('Puissance de la machine (kW):')
        self.power_field = QLineEdit()
        self.usage_time_label = QLabel("Temps d'utilisation par jour (heures):")
        self.usage_time_field = QLineEdit()
        self.days_machine_label = QLabel("Nombre de jours d'utilisation:")
        self.days_machine_field = QLineEdit()
        self.electricity_label = QLabel("Type d'électricité:")
        self.electricity_combo = QComboBox()

        electricity_types = self.main_data[self.main_data['category'] == 'Électricité']['name'].dropna().unique()
        self.electricity_combo.addItems(sorted(electricity_types))

        # Layout pour les catégories normales
        self.normal_form_layout = QFormLayout()
        self.normal_form_layout.addRow(self.category_label, self.category_combo)
        self.normal_form_layout.addRow(self.subcategory_label, self.subcategory_combo)
        self.normal_form_layout.addRow(self.search_label, self.search_field)
        self.normal_form_layout.addRow(self.subsub_name_label, self.subsub_name_combo)
        self.normal_form_layout.addRow(self.year_label, self.year_combo)
        self.normal_form_layout.addRow(self.input_label, self.input_field)
        self.normal_form_layout.addRow(self.days_label, self.days_field)
        self.normal_form_layout.addRow(self.nacres_filtered_label, self.nacres_filtered_combo)
        self.normal_form_layout.addRow(self.quantity_label, self.quantity_input)

        # Layout pour les machines
        self.machine_form_layout = QFormLayout()
        self.machine_form_layout.addRow(self.machine_name_label, self.machine_name_field)
        self.machine_form_layout.addRow(self.power_label, self.power_field)
        self.machine_form_layout.addRow(self.usage_time_label, self.usage_time_field)
        self.machine_form_layout.addRow(self.days_machine_label, self.days_machine_field)
        self.machine_form_layout.addRow(self.electricity_label, self.electricity_combo)

        # Un widget pour chaque type d'affichage
        self.normal_widget = QWidget()
        self.normal_widget.setLayout(self.normal_form_layout)

        self.machine_widget = QWidget()
        self.machine_widget.setLayout(self.machine_form_layout)

        # Boutons
        buttons_layout = QHBoxLayout()
        self.validate_button = QPushButton("Valider")
        self.cancel_button = QPushButton("Annuler")
        buttons_layout.addWidget(self.validate_button)
        buttons_layout.addWidget(self.cancel_button)

        # Ajout au layout principal
        layout.addWidget(self.normal_widget)
        layout.addWidget(self.machine_widget)
        layout.addLayout(buttons_layout)

        # Connexions signaux/slots
        self.category_combo.currentIndexChanged.connect(self.update_subcategories)
        self.subcategory_combo.currentIndexChanged.connect(self.update_subsubcategory_names)
        self.search_field.textChanged.connect(self.update_subsubcategory_names)
        self.subsub_name_combo.currentIndexChanged.connect(self.update_years)
        self.year_combo.currentIndexChanged.connect(self.update_unit)
        self.year_combo.currentIndexChanged.connect(self.update_nacres_filtered_combo)
        self.nacres_filtered_combo.currentIndexChanged.connect(self.on_nacres_filtered_changed)

        self.validate_button.clicked.connect(self.on_validate)
        self.cancel_button.clicked.connect(self.reject)

    def populate_fields(self, data):
        """
        Pré-remplit les champs avec les données du calcul existant.
        """
        category = data.get('category', '')
        self.category_combo.setCurrentText(category)
        self.update_subcategories()

        if category == 'Machine':
            # Afficher le widget machine, cacher le widget normal
            self.normal_widget.setVisible(False)
            self.machine_widget.setVisible(True)

            # Pré-remplir les champs machine
            # On suppose que lors de la création de la machine, on a stocké :
            # 'subcategory' = nom de la machine
            # 'value' = total_usage (kWh)
            # 'electricity_type' = type d'électricité
            # Pour re-calculer la puissance, usage_time et days_machine,
            # Il faut les avoir stockés également. Si ce n'est pas le cas,
            # il faut les stocker lors de la création initiale de la machine.
            # Supposons que vous ayez stocké ces infos lors de la création initiale :
            # data['machine_name'], data['power'], data['usage_time'], data['days_machine'], data['electricity_type']

            self.machine_name_field.setText(data.get('subcategory', ''))
            self.power_field.setText(str(data.get('power', '')))
            self.usage_time_field.setText(str(data.get('usage_time', '')))
            self.days_machine_field.setText(str(data.get('days_machine', '')))
            electricity_type = data.get('electricity_type', '')
            if electricity_type:
                self.electricity_combo.setCurrentText(electricity_type)

        else:
            # Afficher le widget normal, cacher le widget machine
            self.normal_widget.setVisible(True)
            self.machine_widget.setVisible(False)

            self.subcategory_combo.setCurrentText(data.get('subcategory', ''))
            self.update_subsubcategory_names()

            subsubcategory = data.get('subsubcategory', '')
            name = data.get('name', '')
            if subsubcategory and name:
                subsub_name = f"{subsubcategory} - {name}"
            else:
                subsub_name = name if name else subsubcategory
            self.subsub_name_combo.setCurrentText(subsub_name)
            self.update_years()

            self.year_combo.setCurrentText(str(data.get('year', '')))

            val = data.get('value', 0)
            self.input_field.setText(str(val))
            self.current_unit = data.get('unit', '')
            if self.current_unit:
                self.input_label.setText(f'Entrez la valeur en {self.current_unit}:')
                self.input_field.setEnabled(True)

            # Jours
            if data.get('category', '') == 'Véhicules' or data.get('days', None) is not None:
                self.days_label.setVisible(True)
                self.days_field.setVisible(True)
                self.days_field.setEnabled(True)
                self.days_field.setText(str(data.get('days', 1)))
            else:
                self.days_label.setVisible(False)
                self.days_field.setVisible(False)

            # NACRES filtrés
            if data.get('category') == 'Achats' and 'Consommables' in data.get('subcategory', ''):
                self.update_nacres_filtered_combo()
                code_nacres = data.get('code_nacres', '')
                consommable = data.get('consommable', '')
                if code_nacres and consommable:
                    nacres_text = f"{code_nacres} - {consommable}"
                    index = self.nacres_filtered_combo.findText(nacres_text)
                    if index >= 0:
                        self.nacres_filtered_combo.setCurrentIndex(index)
                        self.quantity_label.setVisible(True)
                        self.quantity_input.setVisible(True)
                        # Remplir la quantité si on l'avait stockée
                        quantity = data.get('quantity', None)
                        if quantity is not None:
                            self.quantity_input.setText(str(quantity))

    def on_validate(self):
        """
        Récupère les données modifiées et les enregistre dans self.modified_data avant de fermer le dialog.
        """
        category = self.category_combo.currentText()

        if category == 'Machine':
            # Récupération des données machine
            machine_name = self.machine_name_field.text().strip()
            try:
                power = float(self.power_field.text().strip().replace(',', '.'))
                usage_time = float(self.usage_time_field.text().strip().replace(',', '.'))
                days_machine = int(self.days_machine_field.text().strip())
            except ValueError:
                QMessageBox.warning(self, 'Erreur', "Veuillez entrer des valeurs numériques valides pour la machine.")
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
                'electricity_type': electricity_type
            }

        else:
            # Cas normal
            subcategory = self.subcategory_combo.currentText()
            subsub_name = self.subsub_name_combo.currentText()
            subsubcategory, name = self.split_subsub_name(subsub_name)
            year = self.year_combo.currentText()
            try:
                value = float(self.input_field.text().strip().replace(',', '.'))
            except ValueError:
                QMessageBox.warning(self, 'Erreur', 'Veuillez entrer une valeur numérique.')
                return

            days = 1
            if self.days_field.isVisible() and self.days_field.text().strip():
                try:
                    days = int(self.days_field.text())
                except ValueError:
                    QMessageBox.warning(self, 'Erreur', 'Veuillez entrer un nombre de jours valide.')
                    return

            selected_nacres = self.nacres_filtered_combo.currentText() if self.nacres_filtered_combo.isVisible() else None
            code_nacres = 'NA'
            consommable = 'NA'
            if selected_nacres and selected_nacres != "Aucune correspondance":
                if " - " in selected_nacres:
                    code_nacres, consommable = selected_nacres.split(" - ", 1)

            quantity = None
            if self.quantity_input.isVisible():
                try:
                    quantity_val = int(self.quantity_input.text())
                    if quantity_val <= 0:
                        raise ValueError
                    quantity = quantity_val
                except ValueError:
                    QMessageBox.warning(self, 'Erreur', 'Veuillez entrer une quantité positive.')
                    return

            self.modified_data = {
                'category': category,
                'subcategory': subcategory,
                'subsubcategory': subsubcategory,
                'name': name,
                'year': year,
                'unit': self.current_unit,
                'value': value,
                'days': days,
                'code_nacres': code_nacres,
                'consommable': consommable,
                'quantity': quantity
            }

        self.accept()

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
            # Cacher les champs "normaux" et afficher ceux de la machine
            self.normal_widget.setVisible(False)
            self.machine_widget.setVisible(True)
        else:
            # Afficher les champs normaux et cacher ceux de la machine
            self.normal_widget.setVisible(True)
            self.machine_widget.setVisible(False)
            subcategories = self.main_data[self.main_data['category'] == category]['subcategory'].dropna().unique()
            self.subcategory_combo.clear()
            self.subcategory_combo.addItems(sorted(subcategories.astype(str)))
            self.update_subsubcategory_names()

            # Gérer la visibilité des jours si catégorie Véhicules
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
        subcategory = self.subcategory_combo.currentText()
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
        self.update_unit()

    def update_unit(self):
        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
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
                        nom_objet_val = row["Consommable"]
                        display_text = f"{row['Code NACRES']} - {nom_objet_val}"
                        self.nacres_filtered_combo.addItem(display_text)

            # Toujours ajouter "Aucune correspondance"
            self.nacres_filtered_combo.addItem("Aucune correspondance")
            self.nacres_filtered_combo.setCurrentText("Aucune correspondance")

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