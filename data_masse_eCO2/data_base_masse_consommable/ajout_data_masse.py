# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)

# data_masse_eCO2/data_base_masse_consommable/ajout_data_masse.py

import os
import sys
import pandas as pd

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QWidget, QMessageBox, QComboBox, QHeaderView
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Gestion des matériaux")
        self.resize(1000, 600)

        # 1) Dossier de base : on part du répertoire courant
        base_dir = os.path.abspath(os.getcwd())
        self.nacres_hdf5_file = os.path.join(base_dir, 'data_masse_eCO2', 'nacres_2022.h5')
        self._all_nacres = []  # List of (code, description) tuples

        # 2) Chemins vers les fichiers HDF5
        #    Adapte si ton répertoire n'est pas celui-ci
        self.hdf5_data_path = os.path.join(base_dir, 'data_masse_eCO2', 'data_eCO2_masse_consommable.hdf5')
        self.hdf5_materials_path = os.path.join(base_dir, 'data_masse_eCO2', 'empreinte_carbone_materiaux.h5')

        # 3) Nom des colonnes pour le DataFrame principal
        self.columns = [
            "Consommable",
            "Marque",
            "Référence",
            "Code NACRES",
            "Masse unitaire (g)",
            "Matériau",
            "Source/Signature"
        ]

        # 4) Chargement initial des données
        self.data = self.load_main_data()   # DataFrame principal
        self.materials = self.load_materials()  # Liste de matériaux

        # 5) Prépare l'interface
        self.init_ui()

    def load_main_data(self) -> pd.DataFrame:
        """
        Charge le DataFrame principal depuis le fichier HDF5.
        Si le fichier n'existe pas ou la clé n'existe pas, on crée un DataFrame vide et on le sauvegarde.
        """
        try:
            if not os.path.exists(self.hdf5_data_path):
                # Fichier absent : on crée un DF vide et on l'enregistre
                print(f"[INFO] Le fichier {self.hdf5_data_path} n'existe pas. Création d'un fichier vide.")
                empty_df = pd.DataFrame(columns=self.columns)
                empty_df.to_hdf(self.hdf5_data_path, key='data', mode='w')
                return empty_df

            # Lecture du HDF5
            df = pd.read_hdf(self.hdf5_data_path, key='data')
            print("[INFO] Données chargées depuis", self.hdf5_data_path)
            print(df)  # Debug console : affiche le contenu
            return df

        except (FileNotFoundError, KeyError) as e:
            # On crée un fichier HDF5 vide si la clé "data" n'existe pas
            print(f"[WARNING] Problème lors du chargement : {e}. Création d'un nouveau DataFrame vide.")
            empty_df = pd.DataFrame(columns=self.columns)
            empty_df.to_hdf(self.hdf5_data_path, key='data', mode='w')
            return empty_df
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur inattendue lors du chargement HDF5.\n{e}")
            return pd.DataFrame(columns=self.columns)

    def load_materials(self) -> list:
        """
        Charge la liste des matériaux depuis un autre fichier HDF5 (optionnel).
        Retourne une liste (vide si aucun fichier / aucune info).
        """
        try:
            if not os.path.exists(self.hdf5_materials_path):
                print(f"[INFO] Fichier {self.hdf5_materials_path} introuvable. Liste de matériaux vide.")
                return []

            df_mat = pd.read_hdf(self.hdf5_materials_path, key='data')
            # On suppose qu'il y a une colonne "Materiau" qu'on veut lister
            materials = df_mat["Materiau"].drop_duplicates().sort_values().tolist()
            print("[INFO] Matériaux chargés :", materials)
            return materials
        except Exception as e:
            print(f"[ERROR] Impossible de charger la liste des matériaux : {e}")
            return []

    def load_nacres_list(self):
        if not os.path.exists(self.nacres_hdf5_file):
            print(f"[INFO] Fichier {self.nacres_hdf5_file} introuvable. Impossible de charger la liste NACRES.")
            return

        try:
            df_nacres = pd.read_hdf(self.nacres_hdf5_file)
            self._all_nacres = []
            for _, row in df_nacres.iterrows():
                code = str(row.iloc[0])
                desc = str(row.iloc[1])
                self._all_nacres.append((code, desc))
            self.filter_nacres_list()  # Populate the combo box for the first time
        except Exception as e:
            print(f"[ERROR] Impossible de charger la liste NACRES : {e}")

    def filter_nacres_list(self):
        search_text = self.nacre_search.text().strip().lower()
        self.nacre_combo.clear()

        for (code, desc) in self._all_nacres:
            if search_text in code.lower() or search_text in desc.lower():
                display_text = f"{code} - {desc}"
                self.nacre_combo.addItem(display_text, code)

    def init_ui(self):
        """Construit la fenêtre PySide6 : form + table."""
        # Layout principal
        main_layout = QVBoxLayout()

        # ==== Formulaire d'ajout ====
        form_layout = QFormLayout()

        self.nom_input = QLineEdit()
        self.brand_input = QLineEdit()
        self.ref_input = QLineEdit()
        self.masse_input = QLineEdit()
        self.materiau_combo = QComboBox()
        self.materiau_combo.addItems(self.materials)
        self.source_input = QLineEdit()
        self.nacre_combo = QComboBox()
        form_layout.addRow("Consommable :", self.nom_input)
        form_layout.addRow("Marque :", self.brand_input)
        form_layout.addRow("Référence :", self.ref_input)

        nacre_layout = QVBoxLayout()
        nacre_layout.addWidget(self.nacre_combo)

        search_layout = QVBoxLayout()
        search_label = QLabel("Rechercher un code NACRES :")
        search_layout.addWidget(search_label)
        self.nacre_search = QLineEdit()
        search_layout.addWidget(self.nacre_search)

        nacre_layout.addLayout(search_layout)
        form_layout.addRow("Code NACRES :", nacre_layout)

        form_layout.addRow("Masse unitaire (g) :", self.masse_input)
        form_layout.addRow("Matériau :", self.materiau_combo)
        form_layout.addRow("Source/Signature :", self.source_input)

        main_layout.addLayout(form_layout)

        # ==== Boutons ====
        self.add_button = QPushButton("Ajouter l'objet")
        self.add_button.clicked.connect(self.ajouter_objet)
        main_layout.addWidget(self.add_button)

        self.display_button = QPushButton("Afficher les données")
        self.display_button.clicked.connect(self.afficher_donnees)
        main_layout.addWidget(self.display_button)

        # ==== Tableau des données ====
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        main_layout.addWidget(self.table)

        # Conteneur principal
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Connect the search bar
        self.nacre_search.textChanged.connect(self.filter_nacres_list)

        # Après la création de l'interface, on montre les données existantes
        self.load_nacres_list()
        self.afficher_donnees()

    def ajouter_objet(self):
        """
        Récupère les infos du formulaire, crée une ligne dans le DataFrame,
        sauve dans le fichier HDF5, puis met à jour l'affichage.
        """
        nom = self.nom_input.text().strip()
        marque = self.brand_input.text().strip()
        reference = self.ref_input.text().strip()
        masse_str = self.masse_input.text().replace(',', '.').strip()
        materiau = self.materiau_combo.currentText()
        source = self.source_input.text().strip()
        nacre = self.nacre_combo.currentData()
        if not nacre:
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un code NACRES.")
            return

        # Vérifications basiques
        if not nom or not reference or not materiau or not source:
            QMessageBox.warning(self, "Erreur", "Veuillez remplir tous les champs obligatoires.")
            return

        try:
            masse = float(masse_str)
        except ValueError:
            QMessageBox.warning(self, "Erreur", "La masse unitaire doit être un nombre (ex: 14.35).")
            return

        # Créer un nouvel enregistrement
        new_line = {
            "Consommable": nom,
            "Marque": marque,
            "Référence": reference,
            "Code NACRES": nacre,
            "Masse unitaire (g)": masse,
            "Matériau": materiau,
            "Source/Signature": source
        }

        # Ajouter la nouvelle ligne au DF existant
        self.data = pd.concat([self.data, pd.DataFrame([new_line])], ignore_index=True)

        # Sauvegarde HDF5
        try:
            self.data.to_hdf(self.hdf5_data_path, key='data', mode='w')
            QMessageBox.information(self, "Succès", f"L'objet '{nom}' a bien été ajouté.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'écrire dans le fichier HDF5.\n{e}")

        # Effacer les champs
        self.nom_input.clear()
        self.brand_input.clear()
        self.ref_input.clear()
        self.masse_input.clear()
        self.source_input.clear()
        if self.materiau_combo.count() > 0:
            self.materiau_combo.setCurrentIndex(0)
        if self.nacre_combo.count() > 0:
            self.nacre_combo.setCurrentIndex(0)

        # Mettre à jour le tableau
        self.afficher_donnees()

    def afficher_donnees(self):
        """Relit le HDF5 et affiche son contenu dans le QTableWidget."""
        try:
            # On relit le fichier HDF5 pour être sûr d'avoir les données à jour
            self.data = pd.read_hdf(self.hdf5_data_path, key='data')
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de lire le HDF5.\n{e}")
            return

        # Ajuster la table
        self.table.setRowCount(len(self.data))

        for row_idx, row_data in self.data.iterrows():
            for col_idx, col_name in enumerate(self.columns):
                val = str(row_data.get(col_name, "N/A"))
                item = QTableWidgetItem(val)
                self.table.setItem(row_idx, col_idx, item)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()