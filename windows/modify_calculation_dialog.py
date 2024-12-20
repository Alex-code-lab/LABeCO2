# windows/modify_calculation_dialog.py

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QMessageBox, QFormLayout
)
from PySide6.QtCore import Qt, Signal
import pandas as pd

class ModifyCalculationDialog(QDialog):
    # Signal pour notifier que les données ont été modifiées
    data_modified = Signal(dict)

    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.setWindowTitle("Modifier le Calcul")
        self.setModal(True)
        self.data = data or {}
        self.parent_window = parent
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        form_layout = QFormLayout()

        # 1. Catégorie
        self.category_label = QLabel("Catégorie:")
        self.category_combo = QComboBox()
        categories = sorted(self.parent_window.data['category'].dropna().unique().tolist())
        self.category_combo.addItems(categories)
        self.category_combo.setCurrentText(self.data.get('category', ''))
        form_layout.addRow(self.category_label, self.category_combo)

        # 2. Sous-catégorie
        self.subcategory_label = QLabel("Sous-catégorie:")
        self.subcategory_combo = QComboBox()
        form_layout.addRow(self.subcategory_label, self.subcategory_combo)

        # 3. Sous-sous-catégorie ou Nom
        self.subsub_name_label = QLabel("Sous-sous-catégorie - Nom:")
        self.subsub_name_combo = QComboBox()
        form_layout.addRow(self.subsub_name_label, self.subsub_name_combo)

        # 4. Année
        self.year_label = QLabel("Année:")
        self.year_combo = QComboBox()
        form_layout.addRow(self.year_label, self.year_combo)

        # 5. Valeur (visible seulement si nécessaire)
        self.input_label = QLabel("Entrez la valeur:")
        self.input_field = QLineEdit()
        self.input_field.setText(str(self.data.get('value', '')))
        form_layout.addRow(self.input_label, self.input_field)

        # 6. Nombre de jours (si applicable)
        self.days_label = QLabel("Nombre de jours d'utilisation:")
        self.days_field = QLineEdit()
        self.days_field.setText(str(self.data.get('days', '1')))
        form_layout.addRow(self.days_label, self.days_field)

        # 7. Nombre de kilomètres (si applicable) - Exemple pour les véhicules
        self.kilometers_label = QLabel("Nombre de kilomètres:")
        self.kilometers_field = QLineEdit()
        self.kilometers_field.setText(str(self.data.get('kilometers', '0')))
        form_layout.addRow(self.kilometers_label, self.kilometers_field)

        # 8. Nombre de litres (si applicable) - Exemple pour certains véhicules
        self.liters_label = QLabel("Nombre de litres utilisés:")
        self.liters_field = QLineEdit()
        self.liters_field.setText(str(self.data.get('liters', '0')))
        form_layout.addRow(self.liters_label, self.liters_field)

        # 9. Nombre d'objets (si applicable) - Exemple pour Achats Consommables avec code NACRES
        self.objects_label = QLabel("Nombre d'objets:")
        self.objects_field = QLineEdit()
        self.objects_field.setText(str(self.data.get('objects', '1')))
        form_layout.addRow(self.objects_label, self.objects_field)

        # Masquer les champs non pertinents par défaut
        self.input_label.setVisible(False)
        self.input_field.setVisible(False)
        self.days_label.setVisible(False)
        self.days_field.setVisible(False)
        self.kilometers_label.setVisible(False)
        self.kilometers_field.setVisible(False)
        self.liters_label.setVisible(False)
        self.liters_field.setVisible(False)
        self.objects_label.setVisible(False)
        self.objects_field.setVisible(False)

        layout.addLayout(form_layout)

        # Boutons OK et Annuler
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("OK")
        self.cancel_button = QPushButton("Annuler")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Connexion des signaux/slots après la création des widgets
        self.category_combo.currentIndexChanged.connect(self.update_fields_visibility)
        self.category_combo.currentIndexChanged.connect(self.update_subcategories)
        self.subcategory_combo.currentIndexChanged.connect(self.update_subsubcategory_names)
        self.subsub_name_combo.currentIndexChanged.connect(self.update_years)

        # Initialiser les champs avec les données existantes
        self.populate_initial_data()

    def populate_initial_data(self):
        """
        Remplit les champs de la fenêtre de dialogue avec les données existantes.
        """
        # Mettre à jour les sous-catégories en fonction de la catégorie sélectionnée
        self.update_subcategories()

        # Définir le texte actuel de la sous-catégorie
        self.subcategory_combo.setCurrentText(self.data.get('subcategory', ''))

        # Mettre à jour les sous-sous-catégories en fonction de la sous-catégorie sélectionnée
        self.update_subsubcategory_names()

        # Définir le texte actuel de la sous-sous-catégorie
        subsub_name = f"{self.data.get('subsubcategory', '')} - {self.data.get('name', '')}" if self.data.get('subsubcategory') else self.data.get('name', '')
        self.subsub_name_combo.setCurrentText(subsub_name)

        # Mettre à jour les années en fonction de la sous-sous-catégorie sélectionnée
        self.update_years()

        # Définir l'année actuelle
        self.year_combo.setCurrentText(str(self.data.get('year', '')))

        # Définir la visibilité des champs en fonction de la catégorie initiale
        self.update_fields_visibility()

        # Remplir les autres champs spécifiques
        self.fill_specific_fields()

    def fill_specific_fields(self):
        """
        Remplit les champs spécifiques en fonction des données existantes.
        """
        category = self.data.get('category', '')
        subcategory = self.data.get('subcategory', '')
        subsubcategory = self.data.get('subsubcategory', '')
        name = self.data.get('name', '')
        code_nacres = self.data.get('code_nacres', 'NA')

        if category == 'Véhicules':
            # Selon le type de véhicule, activer les champs appropriés
            # Supposons que la présence de 'kilometers' ou 'liters' détermine le type
            if 'kilometers' in self.data and self.data['kilometers'] > 0:
                self.kilometers_field.setText(str(self.data['kilometers']))
                self.kilometers_label.setVisible(True)
                self.kilometers_field.setVisible(True)
                self.liters_label.setVisible(False)
                self.liters_field.setVisible(False)
            elif 'liters' in self.data and self.data['liters'] > 0:
                self.liters_field.setText(str(self.data['liters']))
                self.liters_label.setVisible(True)
                self.liters_field.setVisible(True)
                self.kilometers_label.setVisible(False)
                self.kilometers_field.setVisible(False)

        if category == 'Achats Consommables':
            # Si code NACRES est présent et différent de 'NA', afficher le champ 'objects'
            if code_nacres != 'NA':
                self.objects_label.setVisible(True)
                self.objects_field.setVisible(True)
            else:
                self.objects_label.setVisible(False)
                self.objects_field.setVisible(False)

    def update_fields_visibility(self):
        """
        Affiche ou masque les champs supplémentaires en fonction de la catégorie sélectionnée.
        """
        category = self.category_combo.currentText()
        if category == 'Véhicules':
            self.input_label.setVisible(False)
            self.input_field.setVisible(False)
            self.days_label.setVisible(True)
            self.days_field.setVisible(True)
            # Les champs 'kilometers' et 'liters' sont gérés séparément
            # Par défaut, masquer les deux, ils seront affichés selon les données
            self.kilometers_label.setVisible(False)
            self.kilometers_field.setVisible(False)
            self.liters_label.setVisible(False)
            self.liters_field.setVisible(False)
            self.objects_label.setVisible(False)
            self.objects_field.setVisible(False)
        elif category == 'Achats Consommables':
            self.input_label.setVisible(True)
            self.input_field.setVisible(True)
            self.days_label.setVisible(False)
            self.days_field.setVisible(False)
            self.kilometers_label.setVisible(False)
            self.kilometers_field.setVisible(False)
            # Le champ 'objects' sera affiché si 'code_nacres' est présent
            if self.data.get('code_nacres') and self.data.get('code_nacres') != 'NA':
                self.objects_label.setVisible(True)
                self.objects_field.setVisible(True)
            else:
                self.objects_label.setVisible(False)
                self.objects_field.setVisible(False)
        else:
            # Pour les autres catégories
            self.input_label.setVisible(True)
            self.input_field.setVisible(True)
            self.days_label.setVisible(False)
            self.days_field.setVisible(False)
            self.kilometers_label.setVisible(False)
            self.kilometers_field.setVisible(False)
            self.liters_label.setVisible(False)
            self.liters_field.setVisible(False)
            self.objects_label.setVisible(False)
            self.objects_field.setVisible(False)

    def update_subcategories(self):
        category = self.category_combo.currentText()
        if category == 'Machine':
            self.subcategory_combo.clear()
            self.subcategory_combo.setEnabled(False)
            self.subsub_name_combo.clear()
            self.subsub_name_combo.setEnabled(False)
            self.year_combo.clear()
            self.year_combo.setEnabled(False)
            self.update_fields_visibility()
            return
        else:
            self.subcategory_combo.setEnabled(True)
            subcategories = self.parent_window.data[self.parent_window.data['category'] == category]['subcategory'].dropna().unique().tolist()
            self.subcategory_combo.clear()
            self.subcategory_combo.addItems(sorted(subcategories))
            self.update_subsubcategory_names()

    def update_subsubcategory_names(self):
        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        if category == 'Machine':
            self.subsub_name_combo.clear()
            self.subsub_name_combo.setEnabled(False)
            self.year_combo.clear()
            self.year_combo.setEnabled(False)
            self.update_fields_visibility()
            return
        else:
            self.subsub_name_combo.setEnabled(True)
            mask = (self.parent_window.data['category'] == category) & (self.parent_window.data['subcategory'] == subcategory)
            filtered_data = self.parent_window.data[mask]
            subsub_names = (filtered_data['subsubcategory'].fillna('') + ' - ' + filtered_data['name'].fillna('')).str.strip(' - ')
            subsub_names_unique = subsub_names.unique().tolist()
            self.subsub_name_combo.clear()
            self.subsub_name_combo.addItems(sorted(subsub_names_unique))
            self.update_years()

    def update_years(self):
        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        subsub_name = self.subsub_name_combo.currentText()
        if category == 'Machine':
            self.year_combo.clear()
            self.year_combo.setEnabled(False)
            return
        if ' - ' in subsub_name:
            subsubcategory, name = self.parent_window.split_subsub_name(subsub_name)
        else:
            subsubcategory, name = subsub_name, ''
        mask = (
            (self.parent_window.data['category'] == category) &
            (self.parent_window.data['subcategory'] == subcategory) &
            (self.parent_window.data['subsubcategory'].fillna('') == subsubcategory) &
            (self.parent_window.data['name'].fillna('') == name)
        )
        years = self.parent_window.data[mask]['year'].dropna().astype(str).unique().tolist()
        self.year_combo.clear()
        self.year_combo.addItems(sorted(years))
        self.update_unit()

    def update_unit(self):
        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        subsub_name = self.subsub_name_combo.currentText()
        year = self.year_combo.currentText()
        if category == 'Machine':
            self.current_unit = None
            self.input_label.setText('Entrez la valeur:')
            self.input_field.setEnabled(False)
            return
        subsubcategory, name = self.parent_window.split_subsub_name(subsub_name)

        mask = (
            (self.parent_window.data['category'] == category) &
            (self.parent_window.data['subcategory'] == subcategory) &
            (self.parent_window.data['subsubcategory'].fillna('') == subsubcategory) &
            (self.parent_window.data['name'].fillna('') == name) &
            (self.parent_window.data['year'].astype(str) == year)
        )

        filtered_data = self.parent_window.data[mask]
        if not filtered_data.empty:
            unit = filtered_data['unit'].values[0] or 'valeur'
            self.current_unit = unit
            self.input_label.setText(f'Entrez la valeur en {unit}:')
            self.input_field.setEnabled(True)
        else:
            self.current_unit = None
            self.input_label.setText('Entrez la valeur:')
            self.input_field.setEnabled(False)

    def accept(self):
        """
        Surcharge de la méthode accept pour valider et transmettre les données modifiées.
        """
        # Récupérer les valeurs des champs
        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        subsub_name = self.subsub_name_combo.currentText()
        year = self.year_combo.currentText()
        value_text = self.input_field.text().strip()
        days_text = self.days_field.text().strip()
        kilometers_text = self.kilometers_field.text().strip()
        liters_text = self.liters_field.text().strip()
        objects_text = self.objects_field.text().strip()

        # Validation des champs obligatoires
        if not category:
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner une catégorie.")
            return
        if category != 'Machine' and not subcategory:
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner une sous-catégorie.")
            return
        if category != 'Machine' and not subsub_name:
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner une sous-sous-catégorie et un nom.")
            return
        if category != 'Machine' and not year:
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner une année.")
            return
        if category not in ['Véhicules', 'Achats Consommables'] and not value_text:
            QMessageBox.warning(self, "Erreur", "Veuillez entrer une valeur.")
            return

        # Conversion des champs numériques
        try:
            value = float(value_text.replace(',', '.')) if value_text else 0
            if category not in ['Véhicules', 'Achats Consommables'] and value <= 0:
                raise ValueError("La valeur doit être positive.")
        except ValueError:
            QMessageBox.warning(self, "Erreur", "Veuillez entrer une valeur numérique positive valide.")
            return

        days = 1  # Valeur par défaut
        if category == 'Véhicules':
            try:
                days = int(days_text)
                if days <= 0:
                    raise ValueError("Le nombre de jours doit être positif.")
            except ValueError:
                QMessageBox.warning(self, "Erreur", "Veuillez entrer un nombre de jours valide.")
                return

        kilometers = 0  # Valeur par défaut
        if category == 'Véhicules':
            try:
                kilometers = float(kilometers_text.replace(',', '.'))
                if kilometers < 0:
                    raise ValueError("Le nombre de kilomètres doit être positif.")
            except ValueError:
                QMessageBox.warning(self, "Erreur", "Veuillez entrer un nombre de kilomètres valide.")
                return

        liters = 0  # Valeur par défaut
        if category == 'Véhicules':
            try:
                liters = float(liters_text.replace(',', '.'))
                if liters < 0:
                    raise ValueError("Le nombre de litres doit être positif.")
            except ValueError:
                QMessageBox.warning(self, "Erreur", "Veuillez entrer un nombre de litres valide.")
                return

        objects = 1  # Valeur par défaut
        if category == 'Achats Consommables' and self.data.get('code_nacres') and self.data.get('code_nacres') != 'NA':
            try:
                objects = int(objects_text)
                if objects <= 0:
                    raise ValueError("Le nombre d'objets doit être positif.")
            except ValueError:
                QMessageBox.warning(self, "Erreur", "Veuillez entrer un nombre d'objets valide.")
                return

        # Récupérer le sous-sous-catégorie et le nom
        if ' - ' in subsub_name:
            subsubcategory, name = self.parent_window.split_subsub_name(subsub_name)
        else:
            subsubcategory, name = '', subsub_name

        # Préparer les données modifiées
        modified_data = {
            'category': category,
            'subcategory': subcategory,
            'subsubcategory': subsubcategory,
            'name': name,
            'year': year,
            'value': value,
            'days': days,
            'kilometers': kilometers,
            'liters': liters,
            'objects': objects
        }

        # Emit le signal avec les données modifiées
        self.data_modified.emit(modified_data)
        super().accept()