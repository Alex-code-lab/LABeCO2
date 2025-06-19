# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# windows/data_manager.py

import os
import pandas as pd
from utils.data_loader import load_data  # Ajuster si nécessaire selon ta structure

class DataManager:
    """
    Classe pour centraliser la gestion des chemins de fichiers et des noms de colonnes.
    Fournit des méthodes utilitaires pour charger et interagir avec les données.
    """

    # Noms de colonnes standard
    CATEGORY_COL = "category"
    SUBCATEGORY_COL = "subcategory"
    SUBSUBCATEGORY_COL = "subsubcategory"
    NAME_COL = "name"
    YEAR_COL = "year"
    TOTAL_COL = "total"
    UNCERTAINTY_COL = "uncertainty"
    UNIT_COL = "unit"

    # Spécifique NACRES / consommables
    CODE_NACRES_COL = "Code NACRES"
    CONSOMMABLE_COL = "Consommable"
    MASSE_G_COL = "Masse unitaire (g)"
    MATERIAU_COL = "Matériau consommable"
    # Second matériau pour le consommable
    MASSE_G2_COL      = "Masse unitaire deuxieme materiaux (g)"
    MATERIAU2_COL     = "Matériau deuxieme materiaux"
    MASSE_EMBALLAGE_COL = "Masse emballage unitaire (g)"
    MATERIAU_EMBALLAGE_COL = "Matériau emballage"
    MASSE_CONDITIONNEMENT_COL = "Masse condionnement (g)"
    MATERIAU_CONDITIONNEMENT_COL = "Matériau conditionnement"
    NOMBRE_PAR_COND_COL = "Nbr par conditionnement"

    # Spécifique matériaux
    MATERIAU_NAME_COL = "Materiau"
    EQUIV_CO2_COL = "Equivalent CO₂ (kg eCO₂/kg)"

    # Chemins par défaut
    DATA_MASSE_FILENAME = "data_eCO2_masse_consommable.hdf5"
    DATA_MATERIALS_FILENAME = "empreinte_carbone_materiaux.h5"
    DATA_LIQUID_CONSOMMABLES = "data_eCO2_liquides_consommable.hdf5"


    def __init__(self, base_path):
        """
        :param base_path: Répertoire de base pour charger les fichiers de données.
        """
        self.base_path = base_path

        # Charger la data principale
        self.main_data = load_data()  # ta fonction existante, ex. pour "category", "subcategory", etc.

        # Construire les chemins
        self.data_masse_path = os.path.join(base_path, "data_masse_eCO2", self.DATA_MASSE_FILENAME)
        self.data_materials_path = os.path.join(base_path, "data_masse_eCO2", self.DATA_MATERIALS_FILENAME)

        # Charger data_masse
        if not os.path.exists(self.data_masse_path):
            raise FileNotFoundError(f"Fichier {self.data_masse_path} introuvable.")
        self.data_masse = pd.read_hdf(self.data_masse_path)
        if self.CODE_NACRES_COL not in self.data_masse.columns:
            raise KeyError(f"La colonne '{self.CODE_NACRES_COL}' est introuvable dans data_masse.")
        # Nettoyage rapide du DataFrame pour supprimer les lignes vides
        self.data_masse.dropna(subset=[self.CONSOMMABLE_COL], inplace=True)

        # Charger data_materials
        if not os.path.exists(self.data_materials_path):
            raise FileNotFoundError(f"Fichier {self.data_materials_path} introuvable.")
        self.data_materials = pd.read_hdf(self.data_materials_path)

        # Charger consommables liquides (produits chimiques / bioproduits)
        self.liq_path = os.path.join(base_path, "data_masse_eCO2", self.DATA_LIQUID_CONSOMMABLES)
        if os.path.exists(self.liq_path):
            self.data_liquides = pd.read_hdf(self.liq_path)
        else:
            self.data_liquides = pd.DataFrame()  # vide si absent

    def get_main_data(self):
        """Retourne la DataFrame principale."""
        return self.main_data

    def get_data_masse(self):
        """Retourne la DataFrame des consommables (NACRES)."""
        return self.data_masse

    def get_data_materials(self):
        """Retourne la DataFrame des matériaux."""
        return self.data_materials

    def get_emission_factor(self, category, subcategory, subsubcategory, name, year=None):
        """
        Extrait le facteur d'émission (self.TOTAL_COL) et son incertitude (self.UNCERTAINTY_COL)
        depuis la data principale.
        """
        df = self.main_data
        mask = (
            (df[self.CATEGORY_COL] == category) &
            (df[self.SUBCATEGORY_COL] == subcategory) &
            (df[self.SUBSUBCATEGORY_COL].fillna('') == subsubcategory) &
            (df[self.NAME_COL].fillna('') == name)
        )
        if year:
            mask &= (df[self.YEAR_COL].astype(str) == str(year))

        filtered = df[mask]
        if filtered.empty:
            return None, None

        emission_factor = filtered[self.TOTAL_COL].iloc[0]
        # On récupère l'incertitude
        uncertainty_series = filtered.get(self.UNCERTAINTY_COL, pd.Series([0.0]))
        factor_uncert = float(uncertainty_series.iloc[0] or 0.0)
        return float(emission_factor), factor_uncert

    def get_material_data(self, material_name):
        """
        Retourne (co2_par_kg, incert_material) pour un matériau.
        """
        import pandas as pd
        
        # Si le nom de matériau est manquant (NaN) ou n'est pas une chaîne, on ne peut pas récupérer de données
        if pd.isna(material_name) or not isinstance(material_name, str):
            return None, None

        df_mat = self.data_materials
        # Comparaison sécurisée via conversion en chaîne et strip
        mask = df_mat[self.MATERIAU_NAME_COL].astype(str).str.strip() == material_name.strip()
        filtered = df_mat[mask]
        if filtered.empty:
            return None, None

        co2_par_kg = float(filtered[self.EQUIV_CO2_COL].iloc[0] or 0.0)
        incert_mat = float(filtered.get(self.UNCERTAINTY_COL, pd.Series([0.0])).iloc[0] or 0.0)
        return co2_par_kg, incert_mat
    
    def get_data_liquides(self):
        """Retourne la DataFrame des consommables liquides."""
        return self.data_liquides

    def get_liquid_data(self, code_nacres):
        """
        Cherche un consommable liquide par code NACRES.
        Retourne la Series de la ligne si trouvée, sinon None.
        """
        if self.data_liquides.empty:
            return None
        df = self.data_liquides
        mask = df[self.CODE_NACRES_COL].astype(str).str.strip() == code_nacres.strip()
        filtered = df[mask]
        return filtered.iloc[0] if not filtered.empty else None