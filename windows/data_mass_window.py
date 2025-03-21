# windows/data_mass_window.py

import os
import pandas as pd
from PySide6.QtWidgets import (
    QMainWindow, QMessageBox, QVBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QWidget, QComboBox, QHBoxLayout, QLabel
)
from PySide6.QtCore import Signal

class DataMassWindow(QMainWindow):
    data_added = Signal()

    def __init__(self, parent=None, data_materials=None):
        super().__init__(parent)

        self.setWindowTitle("Gestion des consommables")
        self.setGeometry(100, 100, 600, 400)

        # Nom du fichier HDF5
        self.hdf5_file = "./data_masse_eCO2/data_eCO2_masse_consommable.hdf5"

        self.columns = ["Consommable",
                        "Référence",
                        "Code NACRES",
                        "Masse unitaire (g)",
                        "Matériau",
                        "Source/Signature",
                        # "Provenance"
                        ]

        # Charger ou initialiser les données
        self.data = self.charger_ou_initialiser_donnees()

        # data_materials transmis par MainWindow
        # data_materials doit contenir 'Materiau' et 'eCO2_kg'
        self.data_materials = data_materials

        self.init_ui()
        self.afficher_donnees()

    def charger_ou_initialiser_donnees(self):
        if os.path.exists(self.hdf5_file):
            try:
                return pd.read_hdf(self.hdf5_file)
            except Exception as e:
                QMessageBox.warning(self, "Erreur", f"Impossible de charger le fichier HDF5 : {e}")
                return pd.DataFrame(columns=self.columns)
        else:
            data = pd.DataFrame([{
                "Consommable": "Tube Falcon 15ml",
                "Référence": "N/A",
                "Code NACRES": "NB13",
                "Masse unitaire (g)": 6.7,
                "Matériau": "Polypropylène (PP)",
                "Source/Signature": "Alexandre Souchaud"
            }], columns=self.columns)

            self.sauvegarder_donnees(data)
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

    def init_ui(self):
        main_layout = QVBoxLayout()

        form_layout = QFormLayout()
        self.nom_input = QLineEdit()
        self.ref_input = QLineEdit()
        self.nacres_input = QLineEdit()
        self.masse_input = QLineEdit()

        # Peupler la liste des matériaux depuis data_materials
        self.materiau_combo = QComboBox()
        if self.data_materials is not None:
            mats = self.data_materials['Materiau'].dropna().unique().tolist()
            self.materiau_combo.addItems(mats)
        else:
            # Liste statique de secours
            self.materiau_combo.addItems(["Polypropylène (PP)", "Polyéthylène (PE)"])

        self.source_input = QLineEdit()

        form_layout.addRow("Consommable:", self.nom_input)
        form_layout.addRow("Référence:", self.ref_input)
        form_layout.addRow("Code NACRES:", self.nacres_input)
        form_layout.addRow("Masse unitaire (g):", self.masse_input)
        form_layout.addRow("Matériau:", self.materiau_combo)
        form_layout.addRow("Source/Signature:", self.source_input)

        main_layout.addLayout(form_layout)

        self.add_button = QPushButton("Ajouter l'objet")
        self.add_button.clicked.connect(self.ajouter_objet_utilisateur)
        main_layout.addWidget(self.add_button)

        self.display_button = QPushButton("Actualiser les données")
        self.display_button.clicked.connect(self.afficher_donnees)
        main_layout.addWidget(self.display_button)


        # Tableau des données
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)

        # Appliquer le style pour avoir le texte en noir
        self.table.setStyleSheet("""
                                QTableWidget { 
                                    color: black; 
                                }
                                QHeaderView::section {
                                    color: black;
                                }
                            """)

        main_layout.addWidget(self.table)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def verifier_existence_objet(self, nom, reference, code_nacres):
        if not self.data[self.data["Consommable"] == nom].empty:
            return f"Un objet avec le nom '{nom}' existe déjà."

        if not self.data[(self.data["Référence"] == reference) & (self.data["Code NACRES"] == code_nacres)].empty:
            return f"La combinaison Référence='{reference}' et Code NACRES='{code_nacres}' existe déjà."

        return None

    def ajouter_objet_utilisateur(self):
        nom = self.nom_input.text().strip()
        reference = self.ref_input.text().strip()
        nacres = self.nacres_input.text().strip()
        masse_str = self.masse_input.text().strip().replace(',', '.')
        materiau = self.materiau_combo.currentText()
        source = self.source_input.text().strip()

        if not nom or not reference or not materiau or not source or not nacres:
            QMessageBox.warning(self, "Erreur", "Tous les champs doivent être remplis.")
            return

        try:
            masse = float(masse_str)
        except ValueError:
            QMessageBox.warning(self, "Erreur", "La masse unitaire doit être un nombre valide.")
            return

        erreur = self.verifier_existence_objet(nom, reference, nacres)
        if erreur:
            QMessageBox.warning(self, "Erreur", erreur)
            return

        nouvel_objet = {
            "Consommable": nom,
            "Référence": reference,
            "Code NACRES": nacres,
            "Masse unitaire (g)": masse,
            "Matériau": materiau,
            "Source/Signature": source
        }
        self.data = self.ajouter_objet_df(self.data, nouvel_objet)

        # Sauvegarde des données
        self.sauvegarder_donnees()

        # Efface les champs
        self.nom_input.clear()
        self.ref_input.clear()
        self.nacres_input.clear()
        self.masse_input.clear()
        self.materiau_combo.setCurrentIndex(0)
        self.source_input.clear()

        QMessageBox.information(self, "Succès", f"L'objet '{nom}' a été ajouté avec succès.")
        self.data_added.emit()

    def ajouter_objet_df(self, df, objet):
        nouvel_objet = pd.DataFrame([objet])
        nouvel_objet = nouvel_objet.reindex(columns=self.columns)

        if df.empty:
            return nouvel_objet
        else:
            return pd.concat([df, nouvel_objet], ignore_index=True)

    def afficher_donnees(self):
        self.table.setRowCount(len(self.data))
        for row_idx, row_data in self.data.iterrows():
            for col_idx, col_name in enumerate(self.columns):
                item = QTableWidgetItem(str(row_data[col_name]))
                self.table.setItem(row_idx, col_idx, item)

    def calculer_eCO2_via_masse(self):
        """
        Calculer l'eCO₂ via masse:
        On utilise la dernière ligne sélectionnée dans le tableau, ou par exemple
        le Code NACRES et le matériau pour retrouver masse et matériau.

        Pour simplifier, on va prendre le dernier objet ajouté ou un objet spécifique.
        Ici, comme exemple, on va calculer pour le dernier objet du tableau.
        """

        if self.data.empty:
            QMessageBox.warning(self, "Erreur", "Aucun consommable disponible.")
            return

        # Récupérer le dernier objet ou la sélection
        # Ici, on prend le dernier objet pour l'exemple
        last_obj = self.data.iloc[-1]

        try:
            quantite_str = self.qty_input.text().strip()
            quantite = int(quantite_str)
        except ValueError:
            QMessageBox.warning(self, "Erreur", "La quantité doit être un entier valide.")
            return

        if quantite <= 0:
            QMessageBox.warning(self, "Erreur", "La quantité doit être positive.")
            return

        masse_g = last_obj["Masse unitaire (g)"]
        materiau = last_obj["Matériau"]

        if self.data_materials is None:
            QMessageBox.warning(self, "Erreur", "Les données matériaux ne sont pas chargées.")
            return

        # Convertir la masse en kg
        masse_kg = masse_g / 1000.0

        # Récupérer l'eCO2 par kg du matériau
        mat_filter = self.data_materials[self.data_materials['Materiau'] == materiau]
        if mat_filter.empty:
            QMessageBox.warning(self, "Erreur", f"Matériau '{materiau}' non trouvé dans data_materials.")
            return

        eCO2_par_kg = mat_filter['eCO2_kg'].values[0]

        # Calcul de l'eCO2 total
        eCO2_total = quantite * masse_kg * eCO2_par_kg

        QMessageBox.information(self, "Calcul eCO₂ via masse",
                        f"Consommable: {last_obj['Consommable']}\n"
                        f"Quantité: {quantite}\n"
                        f"Masse unitaire: {masse_g} g ({masse_kg:.4f} kg)\n"
                        f"Matériau: {materiau}\n"
                        f"eCO₂ par kg matériau: {eCO2_par_kg:.4f} kg CO₂e/kg\n"
                        f"eCO₂ total: {eCO2_total:.4f} kg CO₂e"
                        )