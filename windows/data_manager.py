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
    MATERIAU_COL = "Matériau"

    # Spécifique matériaux
    MATERIAU_NAME_COL = "Materiau"
    EQUIV_CO2_COL = "Equivalent CO₂ (kg eCO₂/kg)"

    # Chemins par défaut
    DATA_MASSE_FILENAME = "data_eCO2_masse_consommable.hdf5"
    DATA_MATERIALS_FILENAME = "empreinte_carbone_materiaux.h5"

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

        # Charger data_materials
        if not os.path.exists(self.data_materials_path):
            raise FileNotFoundError(f"Fichier {self.data_materials_path} introuvable.")
        self.data_materials = pd.read_hdf(self.data_materials_path)

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
        df_mat = self.data_materials
        mask = df_mat[self.MATERIAU_NAME_COL].str.strip() == material_name.strip()
        filtered = df_mat[mask]
        if filtered.empty:
            return None, None

        co2_par_kg = float(filtered[self.EQUIV_CO2_COL].iloc[0] or 0.0)
        incert_mat = float(filtered.get(self.UNCERTAINTY_COL, pd.Series([0.0])).iloc[0] or 0.0)
        return co2_par_kg, incert_mat