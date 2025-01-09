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

        self.nacres_filtered_label = QLabel("Code NACRES Filtré :")
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

    def populate_fields(self, data):
        """
        Pré-remplit les champs avec les données du calcul existant 
        et autorise le changement de catégorie par la suite.
        """
        category = data.get('category', '')
        self.category_combo.setCurrentText(category)

        # Cette méthode gère l'affichage machine vs normal en fonction de la catégorie
        self.update_subcategories()

        # ------------------------------------------------------------------
        #  Cas Machine : on pré-remplit les champs correspondants
        # ------------------------------------------------------------------
        if category == 'Machine':
            self.machine_name_field.setText(data.get('subcategory', ''))
            self.power_field.setText(str(data.get('power', '')))
            self.usage_time_field.setText(str(data.get('usage_time', '')))
            self.days_machine_field.setText(str(data.get('days_machine', '')))

            electricity_type = data.get('electricity_type', '')
            if electricity_type:
                self.electricity_combo.setCurrentText(electricity_type)

            # Pas de return ici, on laisse l'utilisateur libre de rechanger de catégorie
            # plus tard via self.category_combo et update_subcategories().
        
        else:
            # ------------------------------------------------------------------
            #  Cas Achats / Véhicules / Autre : pré-remplir les champs normaux
            # ------------------------------------------------------------------
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
            else:
                self.input_label.setText('Entrez la valeur:')
                self.input_field.setEnabled(False)

            # Gérer la visibilité du champ "Nombre de jours" si Véhicules
            if category == 'Véhicules':
                self.days_label.setVisible(True)
                self.days_field.setVisible(True)
                self.days_field.setEnabled(True)
                self.days_field.setText(str(data.get('days', 1)))
            else:
                self.days_label.setVisible(False)
                self.days_field.setVisible(False)
                self.days_field.setEnabled(False)

            # Si Achats + Consommables => NACRES
            if category == 'Achats' and 'Consommables' in data.get('subcategory', ''):
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
                        quantity = data.get('quantity', None)
                        if quantity is not None:
                            self.quantity_input.setText(str(quantity))
            else:
                # Dans tous les autres cas, masquer NACRES/quantité
                self.nacres_filtered_label.setVisible(False)
                self.nacres_filtered_combo.setVisible(False)
                self.nacres_filtered_combo.clear()
                self.quantity_label.setVisible(False)
                self.quantity_input.setVisible(False)

    def on_validate(self):
        try:
            category = self.category_combo.currentText()
            prev_code_nacres = self.data.get('code_nacres', 'NA')
            prev_consommable = self.data.get('consommable', 'NA')

            # --------------------------------------------------------------------------
            #  CAS "Machine"
            # --------------------------------------------------------------------------
            if category == 'Machine':
                machine_name = self.machine_name_field.text().strip()
                
                # Vérifier et convertir les champs numériques pour la machine
                power_text = self.power_field.text().strip().replace(',', '.')
                usage_time_text = self.usage_time_field.text().strip().replace(',', '.')
                days_machine_text = self.days_machine_field.text().strip()

                print("Machine - power:", repr(power_text), 
                    "usage_time:", repr(usage_time_text), 
                    "days_machine:", repr(days_machine_text))

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
                    'code_nacres': prev_code_nacres,
                    'consommable': prev_consommable,
                }
                self.accept()
                return

            # --------------------------------------------------------------------------
            #  CAS "Achats" ou autre
            # --------------------------------------------------------------------------
            subcategory = self.subcategory_combo.currentText()
            subsub_name = self.subsub_name_combo.currentText()
            subsubcategory, name = self.split_subsub_name(subsub_name)
            year = self.year_combo.currentText()

            # Lecture sécurisée de la valeur principale
            input_text = self.input_field.text().strip().replace(',', '.')
            print("Input value text:", repr(input_text))
            try:
                value = float(input_text)
            except ValueError:
                QMessageBox.warning(self, 'Erreur', 'Veuillez entrer une valeur numérique valide.')
                return

            # Lecture sécurisée du nombre de jours
            days = 1
            if self.days_field.isVisible():
                days_text = self.days_field.text().strip()
                print("Days field text:", repr(days_text))
                if days_text:
                    try:
                        days = int(days_text)
                    except ValueError:
                        QMessageBox.warning(self, 'Erreur', 
                                            'Veuillez entrer un nombre de jours valide.')
                        return

            # Gestion par défaut NACRES
            code_nacres = 'NA'
            consommable = 'NA'
            if category == 'Achats' and subsubcategory:
                code_nacres = subsubcategory[:4]

            if self.nacres_filtered_combo.isVisible():
                selected_nacres = self.nacres_filtered_combo.currentText().strip()
                print("Selected NACRES:", repr(selected_nacres))
                if selected_nacres and selected_nacres != "Aucune correspondance":
                    if " - " in selected_nacres:
                        code_nacres, consommable = selected_nacres.split(" - ", 1)
                elif selected_nacres == "Aucune correspondance":
                    if subsubcategory:
                        code_nacres = subsubcategory[:4]
                    else:
                        code_nacres = 'NA'
                    consommable = 'NA'

            # Lecture sécurisée de la quantité
            quantity = None
            print("Quantité visible ? =>", self.quantity_input.isVisible())
            if self.quantity_input.isVisible():
                q_str = self.quantity_input.text().strip()
                print("Quantity input text:", repr(q_str))
                if not q_str:
                    QMessageBox.warning(self, 'Erreur', 
                                        "Le champ quantité est vide, veuillez saisir un entier.")
                    return
                try:
                    quantity_val = int(q_str)
                    if quantity_val <= 0:
                        raise ValueError
                    quantity = quantity_val
                except ValueError:
                    QMessageBox.warning(self, 'Erreur', 
                                        'Veuillez entrer une quantité positive.')
                    return

            # Assemblage final dans self.modified_data
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
                'quantity': quantity,
            }

            print("Debug - Nouveau self.modified_data :", self.modified_data)
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
            self.subcategory_combo.clear()
            self.subcategory_combo.addItems(sorted(subcategories.astype(str)))

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