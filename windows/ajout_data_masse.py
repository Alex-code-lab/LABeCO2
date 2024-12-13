import sys
import pandas as pd
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QWidget, QMessageBox, QComboBox
)
import os


class DataMassWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Gestion des matériaux")
        self.setGeometry(100, 100, 600, 400)

        # Nom du fichier HDF5
        self.hdf5_file = "./data_mass_eq/data_masse.hdf5"

        # Initialisation des colonnes
        self.columns = ["Nom de l'objet",
                        "Référence",
                        "Code Nacre",
                        "Masse unitaire (g)",
                        "Matériau",
                        "Source/Signature"]

        # Charger ou initialiser les données
        self.data = self.charger_ou_initialiser_donnees()

        # Matériaux disponibles
        self.materials = ["Polypropylène (PP)",
                          "Polyéthylène (PE)",
                          "Polystyrène (PS)",
                          "Polyethylène téréphtalate (PET)",
                          "Polychlorure de vinyle (PVC)",
                          "Polytétrafluoroéthylène (PTFE)",
                          "Polyméthacrylate de méthyle (PMMA)",
                          "Polycarbonate (PC)",
                          "Acier inoxydable",
                          "Aluminium",
                          "Papier",
                          "Carton",
                          "Verre"]

        # Initialisation des widgets
        self.init_ui()

        # Affiche les données initiales
        self.afficher_donnees()

    def charger_ou_initialiser_donnees(self):
        """
        Charge les données depuis un fichier HDF5 s'il existe.
        Sinon, crée un fichier avec une entrée initiale.
        """
        if os.path.exists(self.hdf5_file):
            try:
                return pd.read_hdf(self.hdf5_file)
            except Exception as e:
                QMessageBox.warning(self, "Erreur", f"Impossible de charger le fichier HDF5 : {e}")
                return pd.DataFrame(columns=self.columns)
        else:
            # Crée un DataFrame avec une entrée initiale
            data = pd.DataFrame([{
                "Nom de l'objet": "Tube Falcon 15ml",
                "Référence": "N/A",
                "Code Nacre": "NA634",
                "Masse unitaire (g)": 6.7,
                "Matériau": "Polypropylène (PP)",
                "Source/Signature": "Alexandre Souchaud"
            }], columns=self.columns)

            # Sauvegarde initiale
            self.sauvegarder_donnees(data)
            return data

    def sauvegarder_donnees(self, df=None):
        """
        Sauvegarde les données dans un fichier HDF5.
        Si df est None, sauvegarde self.data.
        """
        if df is None:
            df = self.data
        try:
            df.to_hdf(self.hdf5_file, key='data', mode='w')
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Impossible de sauvegarder le fichier HDF5 : {e}")

    def init_ui(self):
        """Initialise l'interface utilisateur."""
        main_layout = QVBoxLayout()

        # Formulaire
        form_layout = QFormLayout()
        self.nom_input = QLineEdit()
        self.ref_input = QLineEdit()
        self.nacre_input = QLineEdit()
        self.masse_input = QLineEdit()
        self.materiau_combo = QComboBox()
        self.materiau_combo.addItems(self.materials)  # ajout des différents matériaux à une liste défilante
        self.source_input = QLineEdit()

        form_layout.addRow("Nom de l'objet:", self.nom_input)
        form_layout.addRow("Référence:", self.ref_input)
        form_layout.addRow("Code Nacre:", self.nacre_input)
        form_layout.addRow("Masse unitaire (g):", self.masse_input)
        form_layout.addRow("Matériau:", self.materiau_combo)
        form_layout.addRow("Source/Signature:", self.source_input)

        main_layout.addLayout(form_layout)

        # Boutons
        self.add_button = QPushButton("Ajouter l'objet")
        self.add_button.clicked.connect(self.ajouter_objet_utilisateur)
        main_layout.addWidget(self.add_button)

        # Modification du texte du bouton "Afficher les données"
        self.display_button = QPushButton("Actualiser les données")
        self.display_button.clicked.connect(self.afficher_donnees)
        main_layout.addWidget(self.display_button)

        # Tableau des données
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        main_layout.addWidget(self.table)

        # Widget principal
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def verifier_existence_objet(self, nom, reference, code_nacre):
        """Vérifie si un objet avec le même nom ou la même combinaison référence/code nacre existe déjà."""
        if not self.data[self.data["Nom de l'objet"] == nom].empty:
            return f"Un objet avec le nom '{nom}' existe déjà."

        if not self.data[(self.data["Référence"] == reference) & (self.data["Code Nacre"] == code_nacre)].empty:
            return f"La combinaison Référence='{reference}' et Code Nacre='{code_nacre}' existe déjà."

        return None

    def ajouter_objet_utilisateur(self):
        """Ajoute un objet à la base de données via le formulaire."""
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

        erreur = self.verifier_existence_objet(nom, reference, nacre)
        if erreur:
            QMessageBox.warning(self, "Erreur", erreur)
            return

        nouvel_objet = {
            "Nom de l'objet": nom,
            "Référence": reference,
            "Code Nacre": nacre,
            "Masse unitaire (g)": masse,
            "Matériau": materiau,
            "Source/Signature": source
        }
        self.data = self.ajouter_objet_df(self.data, nouvel_objet)

        # Sauvegarde des données dans le fichier HDF5
        self.sauvegarder_donnees()

        # Efface les champs du formulaire
        self.nom_input.clear()
        self.ref_input.clear()
        self.nacre_input.clear()
        self.masse_input.clear()
        self.materiau_combo.setCurrentIndex(0)
        self.source_input.clear()

        QMessageBox.information(self, "Succès", f"L'objet '{nom}' a été ajouté avec succès.")

    def ajouter_objet_df(self, df, objet):
        """Ajoute un objet à un DataFrame de manière sécurisée."""
        nouvel_objet = pd.DataFrame([objet])
        nouvel_objet = nouvel_objet.reindex(columns=self.columns)

        if df.empty:
            return nouvel_objet
        else:
            return pd.concat([df, nouvel_objet], ignore_index=True)

    def afficher_donnees(self):
        """Affiche les données dans le tableau."""
        self.table.setRowCount(len(self.data))
        for row_idx, row_data in self.data.iterrows():
            for col_idx, col_name in enumerate(self.columns):
                item = QTableWidgetItem(str(row_data[col_name]))
                self.table.setItem(row_idx, col_idx, item)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DataMassWindow()
    window.show()
    sys.exit(app.exec())