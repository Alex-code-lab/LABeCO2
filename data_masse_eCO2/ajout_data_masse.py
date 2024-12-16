import sys
import pandas as pd
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QWidget, QMessageBox
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Gestion des matériaux")
        self.setGeometry(100, 100, 600, 400)

        # Initialisation des données
        self.columns = ["Nom de l'objet", "Référence", "Masse unitaire (g)", "Matériau", "Source/Signature"]
        self.data = pd.DataFrame(columns=self.columns)
        self.data = pd.concat([self.data, pd.DataFrame([{
            "Nom de l'objet": "Tube Falcon 15ml",
            "Référence": "N/A",
            "Masse unitaire (g)": 6.7,
            "Matériau": "Polypropylène (PP)",
            "Source/Signature": "Alexandre Souchaud"
        }])], ignore_index=True)

        # Initialisation des widgets
        self.init_ui()

    def init_ui(self):
        """Initialise l'interface utilisateur."""
        main_layout = QVBoxLayout()

        # Formulaire
        form_layout = QFormLayout()
        self.nom_input = QLineEdit()
        self.ref_input = QLineEdit()
        self.masse_input = QLineEdit()
        self.materiau_input = QLineEdit()
        self.source_input = QLineEdit()

        form_layout.addRow("Nom de l'objet:", self.nom_input)
        form_layout.addRow("Référence:", self.ref_input)
        form_layout.addRow("Masse unitaire (g):", self.masse_input)
        form_layout.addRow("Matériau:", self.materiau_input)
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
        main_layout.addWidget(self.table)

        # Widget principal
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def ajouter_objet(self):
        """Ajoute un objet à la base de données."""
        nom = self.nom_input.text().strip()
        reference = self.ref_input.text().strip()
        masse_str = self.masse_input.text().strip().replace(',', '.')
        materiau = self.materiau_input.text().strip()
        source = self.source_input.text().strip()

        if not nom or not reference or not materiau or not source:
            QMessageBox.warning(self, "Erreur", "Tous les champs doivent être remplis.")
            return

        try:
            masse = float(masse_str)
        except ValueError:
            QMessageBox.warning(self, "Erreur", "La masse unitaire doit être un nombre valide.")
            return

        nouvel_objet = {
            "Nom de l'objet": nom,
            "Référence": reference,
            "Masse unitaire (g)": masse,
            "Matériau": materiau,
            "Source/Signature": source
        }
        self.data = pd.concat([self.data, pd.DataFrame([nouvel_objet])], ignore_index=True)

        # Efface les champs du formulaire
        self.nom_input.clear()
        self.ref_input.clear()
        self.masse_input.clear()
        self.materiau_input.clear()
        self.source_input.clear()

        QMessageBox.information(self, "Succès", f"L'objet '{nom}' a été ajouté avec succès.")

    def afficher_donnees(self):
        """Affiche les données dans le tableau."""
        self.table.setRowCount(len(self.data))
        for row_idx, row_data in self.data.iterrows():
            for col_idx, col_name in enumerate(self.columns):
                item = QTableWidgetItem(str(row_data[col_name]))
                self.table.setItem(row_idx, col_idx, item)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())