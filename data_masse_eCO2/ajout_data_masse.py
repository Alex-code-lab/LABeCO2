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
        self.setGeometry(100, 100, 800, 600)

        # Chemins vers les fichiers HDF5
        self.hdf5_data_path = './data_masse_eCO2/data_eCO2_masse_consommable.hdf5'
        self.hdf5_materials_path = './data_masse_eCO2/empreinte_carbone_materiaux.h5'

        # Colonnes du tableau principal
        self.columns = [
            "Consommable", "Référence", "Code NACRES",
            "Masse unitaire (g)", "Matériau", "Source/Signature"
        ]

        # Charger les données principales et la liste des matériaux
        self.data = self.load_main_data()
        self.materials = self.load_materials()

        # Initialisation de l'interface
        self.init_ui()

    def load_main_data(self):
        """Charge les données principales depuis le fichier HDF5."""
        try:
            df = pd.read_hdf(self.hdf5_data_path, key='data')

            # Afficher TOUTES les lignes dans la console
            print(f"Tableau chargé depuis {self.hdf5_data_path}.")
            print(df.to_string())  # <-- Affichage sans troncature

            return df

        except (FileNotFoundError, KeyError):
            print(f"Fichier introuvable ou clé 'data' absente dans {self.hdf5_data_path}. Initialisation d'un tableau vide.")
            empty_df = pd.DataFrame(columns=self.columns)
            empty_df.to_hdf(self.hdf5_data_path, key='data', mode='w')
            return empty_df
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le fichier principal.\nErreur : {e}")
            return pd.DataFrame(columns=self.columns)

    def load_materials(self):
        """Charge la liste des matériaux depuis le fichier HDF5."""
        try:
            df = pd.read_hdf(self.hdf5_materials_path, key='data')
            materials = df['Materiau'].drop_duplicates().sort_values().tolist()
            print(f"Matériaux chargés depuis {self.hdf5_materials_path}.")
            return materials
        except (FileNotFoundError, KeyError):
            print(f"Fichier ou clé 'data' introuvable dans {self.hdf5_materials_path}. Liste des matériaux vide.")
            return []
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger la liste des matériaux.\nErreur : {e}")
            return []

    def init_ui(self):
        """Initialise l'interface utilisateur."""
        main_layout = QVBoxLayout()

        # Formulaire d'ajout
        form_layout = QFormLayout()
        self.nom_input = QLineEdit()
        self.ref_input = QLineEdit()
        self.nacre_input = QLineEdit()
        self.masse_input = QLineEdit()
        self.materiau_combo = QComboBox()
        self.materiau_combo.addItems(self.materials)
        self.source_input = QLineEdit()

        form_layout.addRow("Consommable:", self.nom_input)
        form_layout.addRow("Référence:", self.ref_input)
        form_layout.addRow("Code NACRES:", self.nacre_input)
        form_layout.addRow("Masse unitaire (g):", self.masse_input)
        form_layout.addRow("Matériau:", self.materiau_combo)
        form_layout.addRow("Source/Signature:", self.source_input)

        main_layout.addLayout(form_layout)

        # Boutons
        self.add_button = QPushButton("Ajouter l'objet")
        self.add_button.clicked.connect(self.ajouter_objet)
        main_layout.addWidget(self.add_button)

        self.display_button = QPushButton("Afficher les données")
        self.display_button.clicked.connect(self.afficher_donnees)
        main_layout.addWidget(self.display_button)

        # Tableau des données
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)

        # Ajuster la taille des colonnes pour voir tout le contenu
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        main_layout.addWidget(self.table)

        # Conteneur principal
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Afficher les données initiales
        self.afficher_donnees()

    def ajouter_objet(self):
        """Ajoute un objet à la base de données et met à jour le fichier HDF5."""
        nom = self.nom_input.text().strip()
        reference = self.ref_input.text().strip()
        nacre = self.nacre_input.text().strip()
        masse_str = self.masse_input.text().strip().replace(',', '.')
        materiau = self.materiau_combo.currentText()
        source = self.source_input.text().strip()

        if not nom or not reference or not materiau or not source or not nacre:
            QMessageBox.warning(self, "Erreur", "Tous les champs doivent être remplis.")
            return

        try:
            masse = float(masse_str)
        except ValueError:
            QMessageBox.warning(self, "Erreur", "La masse unitaire doit être un nombre valide.")
            return

        nouvel_objet = {
            "Consommable": nom,
            "Référence": reference,
            "Code NACRES": nacre,
            "Masse unitaire (g)": masse,
            "Matériau": materiau,
            "Source/Signature": source
        }

        # Ajouter le nouvel objet aux données existantes
        self.data = pd.concat([self.data, pd.DataFrame([nouvel_objet])], ignore_index=True)

        # Sauvegarder les données dans le fichier principal HDF5
        try:
            self.data.to_hdf(self.hdf5_data_path, key='data', mode='w')
            QMessageBox.information(self, "Succès", f"L'objet '{nom}' a été ajouté avec succès et sauvegardé.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de l'enregistrement des données.\nErreur : {e}")
            return

        # Effacer les champs du formulaire
        self.nom_input.clear()
        self.ref_input.clear()
        self.nacre_input.clear()
        self.masse_input.clear()
        self.materiau_combo.setCurrentIndex(0)
        self.source_input.clear()

        # Mettre à jour l'affichage
        self.afficher_donnees()

    def afficher_donnees(self):
        """Affiche les données dans le tableau PySide6."""
        self.table.setRowCount(len(self.data))
        for row_idx, row_data in self.data.iterrows():
            for col_idx, col_name in enumerate(self.columns):
                val = str(row_data.get(col_name, "N/A"))
                item = QTableWidgetItem(val)
                self.table.setItem(row_idx, col_idx, item)


if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()