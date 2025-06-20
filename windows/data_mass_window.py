# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
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
        self.nacres_hdf5_file = "./data_masse_eCO2/nacres_2022.h5"  # or adapt path
        self._all_nacres = []  # Will store (code, description)

        # Nom du fichier HDF5
        self.hdf5_file = "./data_masse_eCO2/data_eCO2_masse_consommable.hdf5"

        self.columns = [
            "Consommable",
            "Marque",
            "Référence",
            "Code NACRES",
            "Masse unitaire (g)",
            "Matériau consommable",
            "Masse unitaire deuxieme materiaux (g)",
            "Matériau deuxieme materiaux",
            "Masse emballage unitaire (g)",
            "Matériau emballage",
            "Masse condionnement (g)",
            "Matériau conditionnement",
            "Nbr par conditionnement",
            "Source/Signature",
            "Lien / Note / Remarque",
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
            "Source/Signature",
            "Note"
        ]

        # Fichier pour les consommables liquides
        self.hdf5_liquids = "./data_masse_eCO2/data_eCO2_liquides_consommable.hdf5"

        # Charger ou initialiser les données
        self.data = self.charger_ou_initialiser_donnees()

        # data_materials transmis par MainWindow
        # data_materials doit contenir 'Materiau' et 'eCO2_kg'
        self.data_materials = data_materials

        self.data_liquids = self.load_liquid_df()


        self.init_ui()
        self.afficher_donnees()

    def charger_ou_initialiser_donnees(self):
        if os.path.exists(self.hdf5_file):
            try:
                df = pd.read_hdf(self.hdf5_file)
            except Exception as e:
                QMessageBox.warning(self, "Erreur", f"Impossible de charger le fichier HDF5 : {e}")
                df = pd.DataFrame(columns=self.columns)
        else:
            df = pd.DataFrame([{
                "Consommable": "Tube Falcon 15ml",
                "Marque": "N/A",
                "Référence": "N/A",
                "Code NACRES": "NB13",
                "Masse unitaire (g)": 6.7,
                "Matériau consommable": "Polypropylène (PP)",
                "Masse unitaire deuxieme materiaux (g)": "N/A",
                "Matériau deuxieme materiaux": "N/A",
                "Masse emballage unitaire (g)": "N/A",
                "Matériau emballage": "N/A",
                "Masse condionnement (g)": "N/A",
                "Matériau conditionnement": "N/A",
                "Nbr par conditionnement": "N/A",
                "Source/Signature": "Alexandre Souchaud"
            }], columns=self.columns)
            self.sauvegarder_donnees(df)
        # --- Harmoniser les colonnes manquantes ---
        data = df
        for col in self.columns:
            if col not in data.columns:
                data[col] = ""
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

        self.form_layout = QFormLayout()

        # Sélecteur de type
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Consommable solide", "Consommable liquide"])
        self.type_combo.currentIndexChanged.connect(self.on_type_changed)
        self.form_layout.addRow("Type d'objet :", self.type_combo)
        self.is_liquid = False  # par défaut

        self.nom_input = QLineEdit()
        self.brand_input = QLineEdit()
        self.ref_input = QLineEdit()

        # Définir la liste des matériaux avant toute création de ComboBox qui l'utilise
        if self.data_materials is not None:
            mats = self.data_materials['Materiau'].dropna().unique().tolist()
        else:
            mats = ["Polypropylène (PP)", "Polyéthylène (PE)"]

        # Second matériau (optionnel)
        self.masse2_input = QLineEdit()
        self.materiau2_combo = QComboBox()
        self.materiau2_combo.addItems(mats)

        # Emballage
        self.masse_emb_input = QLineEdit()
        self.mat_emb_combo = QComboBox()
        self.mat_emb_combo.addItems(mats)

        # Conditionnement
        self.masse_cond_input = QLineEdit()
        self.mat_cond_combo = QComboBox()
        self.mat_cond_combo.addItems(mats)
        self.nbr_cond_input = QLineEdit()

        # Lien / Note
        self.lien_input = QLineEdit()

        # Instead of form_layout.addRow("Code NACRES:", self.nacres_input)
        self.nacres_combo = QComboBox()
        nacres_layout = QVBoxLayout()
        nacres_layout.addWidget(self.nacres_combo)

        search_layout = QHBoxLayout()
        search_label = QLabel("Rechercher un code NACRES:")
        search_layout.addWidget(search_label)
        self.nacres_search = QLineEdit()
        search_layout.addWidget(self.nacres_search)

        nacres_layout.addLayout(search_layout)
        self.form_layout.addRow("Code NACRES:", nacres_layout)

        self.masse_input = QLineEdit()

        # Peupler la liste des matériaux depuis data_materials
        self.materiau_combo = QComboBox()
        self.materiau_combo.addItems(mats)

        self.source_input = QLineEdit()

        self.form_layout.addRow("Consommable:", self.nom_input)
        self.form_layout.addRow("Marque:", self.brand_input)
        self.form_layout.addRow("Référence:", self.ref_input)
        self.form_layout.addRow("Masse unitaire (g):", self.masse_input)
        self.form_layout.addRow("Matériau consommable:", self.materiau_combo)
        self.form_layout.addRow("Masse unitaire 2 (g):", self.masse2_input)
        self.form_layout.addRow("Matériau 2:", self.materiau2_combo)

        self.form_layout.addRow("Masse emballage (g):", self.masse_emb_input)
        self.form_layout.addRow("Matériau emballage:", self.mat_emb_combo)

        self.form_layout.addRow("Masse conditionnement (g):", self.masse_cond_input)
        self.form_layout.addRow("Matériau conditionnement:", self.mat_cond_combo)
        self.form_layout.addRow("Nbr par conditionnement:", self.nbr_cond_input)

        self.form_layout.addRow("Lien / Note / Remarque:", self.lien_input)
        self.form_layout.addRow("Source/Signature:", self.source_input)

        # --- Widgets spécifiques Liquide ---
        self.dens_input    = QLineEdit()
        self.conc_input    = QLineEdit()
        self.factor_input  = QLineEdit()
        self.uncert_input  = QLineEdit()

        self.form_layout.addRow("Densité (g/mL):",      self.dens_input)
        self.form_layout.addRow("Concentration (mg/mL):", self.conc_input)
        self.form_layout.addRow("Facteur CO₂ (kg/kg):", self.factor_input)
        self.form_layout.addRow("Incertitude (%) :",    self.uncert_input)

        # Masquer ces lignes initialement
        for w in (self.dens_input, self.conc_input, self.factor_input, self.uncert_input):
            w.setVisible(False)

        main_layout.addLayout(self.form_layout)

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

        # Applique la visibilité initiale (solide)
        self.update_form_visibility()
        self.nacres_search.textChanged.connect(self.filter_nacres_list)
        self.load_nacres_list()

    def on_type_changed(self, idx):
        """Bascule solide/liquide : met à jour visibilité + table."""
        self.is_liquid = (idx == 1)               # 0 = solide, 1 = liquide
        # Recharger le fichier HDF5 liquide à chaque bascule pour afficher les ajouts récents
        if self.is_liquid:
            self.data_liquids = self.load_liquid_df()
        self.update_form_visibility()             # masque/affiche les bons champs
        self.afficher_donnees()                   # recharge la table avec le bon DF

    def load_nacres_list(self):
        if not os.path.exists(self.nacres_hdf5_file):
            print(f"[INFO] Fichier '{self.nacres_hdf5_file}' introuvable.")
            return

        try:
            df_nacres = pd.read_hdf(self.nacres_hdf5_file)
            self._all_nacres = []
            for _, row in df_nacres.iterrows():
                code = str(row.iloc[0])
                desc = str(row.iloc[1])
                self._all_nacres.append((code, desc))
            self.filter_nacres_list()
        except Exception as e:
            print(f"[ERROR] Impossible de charger la liste NACRES: {e}")

    def load_liquid_df(self):
        if os.path.exists(self.hdf5_liquids):
            df_liq = pd.read_hdf(self.hdf5_liquids)
        else:
            df_liq = pd.DataFrame(columns=self.columns_liquids)
        for col in self.columns_liquids:
            if col not in df_liq.columns:
                df_liq[col] = ""
        return df_liq

    def filter_nacres_list(self):
        search_text = self.nacres_search.text().strip().lower()
        self.nacres_combo.clear()
        for (code, desc) in self._all_nacres:
            if search_text in code.lower() or search_text in desc.lower():
                display_text = f"{code} - {desc}"
                self.nacres_combo.addItem(display_text, code)

    def verifier_existence_objet(self, nom, reference, code_nacres):
        if not self.data[self.data["Consommable"] == nom].empty:
            return f"Un objet avec le nom '{nom}' existe déjà."

        if not self.data[(self.data["Référence"] == reference) & (self.data["Code NACRES"] == code_nacres)].empty:
            return f"La combinaison Référence='{reference}' et Code NACRES='{code_nacres}' existe déjà."

        return None

    def ajouter_objet_utilisateur(self):
        is_liq = self.is_liquid
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
        masse_cond_str = self.masse_cond_input.text().strip().replace(',', '.')
        mat_cond     = self.mat_cond_combo.currentText()
        nbr_cond     = self.nbr_cond_input.text().strip()
        lien_note    = self.lien_input.text().strip()
        source = self.source_input.text().strip()

        if is_liq:
            dens       = self.dens_input.text().strip().replace(',', '.')
            conc       = self.conc_input.text().strip().replace(',', '.')
            facteur    = self.factor_input.text().strip().replace(',', '.')
            incert     = self.uncert_input.text().strip().replace(',', '.')
        else:
            dens = conc = facteur = incert = ""

        if is_liq:
            required_ok = all([nom, nacres, dens, facteur, source])
        else:
            required_ok = all([nom, marque, reference, materiau, nacres, masse_str, source])
        if not required_ok:
            QMessageBox.warning(self, "Erreur", "Tous les champs obligatoires doivent être remplis.")
            return

        if not is_liq:
            try:
                masse = float(masse_str)
            except ValueError:
                QMessageBox.warning(self, "Erreur", "La masse unitaire doit être un nombre valide.")
                return

        erreur = self.verifier_existence_objet(nom, reference, nacres)
        if erreur:
            QMessageBox.warning(self, "Erreur", erreur)
            return

        if is_liq:
            nouvel_objet = {
                "Produit": nom,
                "Type": "Liquide",
                "Code NACRES": nacres,
                "CAS": reference,
                "Référence": reference,
                "Unité": "mL",
                "Densité (g/mL)": dens,
                "Concentration (mg/mL)": conc,
                "Facteur CO₂ (kg CO₂e/kg)": facteur,
                "Incertitude (%)": incert,
                "Source/Signature": source,
                "Note": lien_note
            }
        else:
            nouvel_objet = {
                "Consommable": nom,
                "Marque": marque,
                "Référence": reference,
                "Code NACRES": nacres,
                "Masse unitaire (g)": masse_str,
                "Matériau consommable": materiau,
                "Masse unitaire deuxieme materiaux (g)": masse2_str,
                "Matériau deuxieme materiaux": materiau2,
                "Masse emballage unitaire (g)": masse_emb_str,
                "Matériau emballage": mat_emb,
                "Masse condionnement (g)": masse_cond_str,
                "Matériau conditionnement": mat_cond,
                "Nbr par conditionnement": nbr_cond,
                "Lien / Note / Remarque": lien_note,
                "Source/Signature": source
            }
        if is_liq:
            self.save_liquid(nouvel_objet)
        else:
            self.data = self.ajouter_objet_df(self.data, nouvel_objet)
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
        self.masse_cond_input.clear()
        self.mat_cond_combo.setCurrentIndex(0)
        self.nbr_cond_input.clear()
        self.lien_input.clear()
        self.source_input.clear()
        self.nacres_combo.setCurrentIndex(-1)
        self.dens_input.clear()
        self.conc_input.clear()
        self.factor_input.clear()
        self.uncert_input.clear()

        QMessageBox.information(self, "Succès", f"L'objet '{nom}' a été ajouté avec succès.")
        self.data_added.emit()

    def save_liquid(self, obj_dict):
        """Ajoute une ligne au fichier HDF5 des liquides."""
        # Charger ou créer DF
        if os.path.exists(self.hdf5_liquids):
            try:
                df_liq = pd.read_hdf(self.hdf5_liquids)
            except Exception:
                df_liq = pd.DataFrame(columns=self.columns_liquids)
        else:
            df_liq = pd.DataFrame(columns=self.columns_liquids)

        # Assurer toutes les colonnes
        for col in self.columns_liquids:
            if col not in df_liq.columns:
                df_liq[col] = ""

        new_line = pd.DataFrame([obj_dict]).reindex(columns=self.columns_liquids)
        df_liq = pd.concat([df_liq, new_line], ignore_index=True)
        df_liq.to_hdf(self.hdf5_liquids, key='data', mode='w')
        self.data_liquids = df_liq
        if self.is_liquid:
            self.afficher_donnees()

    def ajouter_objet_df(self, df, objet):
        nouvel_objet = pd.DataFrame([objet])
        nouvel_objet = nouvel_objet.reindex(columns=self.columns)

        if df.empty:
            return nouvel_objet
        else:
            return pd.concat([df, nouvel_objet], ignore_index=True)

    def afficher_donnees(self):
        # Réinitialiser le tableau
        self.table.clearContents()
        if self.is_liquid:
            df, cols = self.data_liquids, self.columns_liquids
        else:
            df, cols = self.data, self.columns

        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)

        self.table.setRowCount(len(df))
        for i, (_, row) in enumerate(df.iterrows()):
            for j, col in enumerate(cols):
                self.table.setItem(i, j, QTableWidgetItem(str(row.get(col, ""))))
        self.table.resizeColumnsToContents()
    
    def update_form_visibility(self):
        """Montre/masque les champs en fonction de self.is_liquid."""
        # Champs propres aux solides
        for w in (
            self.masse_input, self.materiau_combo,
            self.masse2_input, self.materiau2_combo,
            self.masse_emb_input, self.mat_emb_combo,
            self.masse_cond_input, self.mat_cond_combo,
            self.nbr_cond_input
        ):
            lab = self.form_layout.labelForField(w)
            if lab:
                lab.setVisible(not self.is_liquid)
            w.setVisible(not self.is_liquid)

        # Champs propres aux liquides
        for w in (
            self.dens_input, self.conc_input,
            self.factor_input, self.uncert_input
        ):
            lab = self.form_layout.labelForField(w)
            if lab:
                lab.setVisible(self.is_liquid)
            w.setVisible(self.is_liquid)

    def calculer_eCO2_via_masse(self):
        """
        Calcule l'eCO2 total en additionnant :
          - matériau principal
          - deuxième matériau (si masse > 0)
          - emballage
          - conditionnement (divisé par Nbr par conditionnement)
        """
        if self.data.empty:
            QMessageBox.warning(self, "Erreur", "Aucun consommable disponible.")
            return

        # Dernière ligne du tableau
        last_obj = self.data.iloc[-1]

        try:
            quantite = int(self.qty_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Erreur", "La quantité doit être un entier valide.")
            return
        if quantite <= 0:
            QMessageBox.warning(self, "Erreur", "La quantité doit être positive.")
            return

        if self.data_materials is None:
            QMessageBox.warning(self, "Erreur", "Les données matériaux ne sont pas chargées.")
            return

        # Rassemble toutes les paires (masse, matériau)
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
            except ValueError:
                masse_g = 0.0
            materiau = str(last_obj.get(col_mat, "")).strip()

            if masse_g <= 0 or materiau == "" or pd.isna(masse_g):
                continue

            # Cas conditionnement : diviser par Nb par cond.
            if col_masse == "Masse condionnement (g)":
                nb = last_obj.get("Nbr par conditionnement", 1)
                try:
                    nb = float(nb) if nb else 1
                    if nb > 0:
                        masse_g /= nb
                except ValueError:
                    pass

            masse_kg = masse_g / 1000.0 * quantite
            total_mass_kg += masse_kg

            # Chercher facteur
            mat_row = self.data_materials[self.data_materials['Materiau'] == materiau]
            if mat_row.empty:
                details.append(f"{materiau}: facteur inconnu → ignoré")
                continue
            facteur = float(mat_row['eCO2_kg'].iloc[0])
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