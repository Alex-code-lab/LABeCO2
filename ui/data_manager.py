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
    CODE_NOM_COL = "Code NOM"
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

    # Colonnes prix catalogue IJM (dans data_masse)
    PRIX_UNITAIRE_COL = "prix_unitaire_ijm"
    PRIX_HT_COL       = "prix_ht_ijm"
    CONDT_IJM_COL     = "condt_ijm"
    NB_UNITES_IJM_COL = "nb_unites_ijm"

    # Chemins par défaut
    DATA_MASSE_FILENAME = "data_eCO2_masse_consommable.hdf5"
    DATA_MATERIALS_FILENAME = "empreinte_carbone_materiaux.h5"
    DATA_LIQUID_CONSOMMABLES = "data_eCO2_liquides_consommable.hdf5"


    def __init__(self, base_path, user_path=None):
        """
        :param base_path: Répertoire des données en lecture seule (bundlées).
        :param user_path: Répertoire des données modifiables (persistant).
                          Si None, identique à base_path (mode développement).
        """
        self.base_path = base_path
        self.user_path = user_path if user_path is not None else base_path

        # Charger la data principale
        self.main_data = load_data()

        # Données modifiables → user_path
        self.data_masse_path = os.path.join(self.user_path, "data", "mass_factors", self.DATA_MASSE_FILENAME)
        # Données en lecture seule → base_path
        self.data_materials_path = os.path.join(base_path, "data", "mass_factors", self.DATA_MATERIALS_FILENAME)

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
        self.liq_path = os.path.join(self.user_path, "data", "mass_factors", self.DATA_LIQUID_CONSOMMABLES)
        if os.path.exists(self.liq_path):
            self.data_liquides = pd.read_hdf(self.liq_path)
        else:
            self.data_liquides = pd.DataFrame()  # vide si absent

        # Charger les prix du catalogue IJM (optionnel)
        self.data_prix_ijm = self._load_prix_ijm()

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

        raw_co2 = filtered[self.EQUIV_CO2_COL].iloc[0]
        co2_par_kg = 0.0 if pd.isna(raw_co2) else float(raw_co2)
        raw_unc = filtered.get(self.UNCERTAINTY_COL, pd.Series([0.0])).iloc[0]
        incert_mat = 0.0 if pd.isna(raw_unc) else float(raw_unc)
        return co2_par_kg, incert_mat
    
    def get_data_liquides(self):
        """Retourne la DataFrame des consommables liquides."""
        return self.data_liquides

    def _load_prix_ijm(self):
        """
        Charge le CSV des prix du catalogue IJM.
        Cherche dans Scrapping/output/ (dev) puis data_prix/ (production).
        Retourne un DataFrame vide si absent.
        """
        candidates = [
            os.path.join(self.base_path, "tools", "scraping", "output", "prix_ijm_2025.csv"),
            os.path.join(self.base_path, "data_prix", "prix_ijm_2025.csv"),
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    df = pd.read_csv(path, dtype={"code_nacres": str, "designation": str})
                    df["code_nacres"] = df["code_nacres"].fillna("").str.strip()
                    return df
                except Exception:
                    pass
        return pd.DataFrame()

    def get_code_nom(self, code_nacres_full, consommable_name):
        """
        Retourne le Code NOM (code NACRES IJM, ex: 'HA01') correspondant à un consommable
        identifié par son Code NACRES complet et son nom.
        """
        if self.CODE_NOM_COL not in self.data_masse.columns:
            return None
        mask = (
            (self.data_masse[self.CODE_NACRES_COL].astype(str).str.strip() == code_nacres_full.strip()) &
            (self.data_masse[self.CONSOMMABLE_COL].astype(str).str.strip() == consommable_name.strip())
        )
        filtered = self.data_masse[mask]
        if filtered.empty:
            return None
        return str(filtered[self.CODE_NOM_COL].iloc[0]).strip()

    def get_prix_unitaire(self, code_nacres, consommable_name=""):
        """
        Retourne (prix_unitaire, consommable, condt) depuis data_masse.
        Recherche par Code NACRES (4 chars) puis fuzzy match sur le nom.
        Retourne (None, None, None) si aucun prix disponible.
        """
        import pandas as pd
        from difflib import SequenceMatcher

        code = str(code_nacres).strip().upper()
        df = self.data_masse

        mask = df[self.CODE_NACRES_COL].astype(str).str.strip().str.upper() == code
        candidates = df[mask]

        if candidates.empty:
            return None, None, None

        # Garder seulement les lignes avec un prix
        has_price = (
            candidates[self.PRIX_UNITAIRE_COL].notna() &
            (candidates[self.PRIX_UNITAIRE_COL].astype(str).str.strip() != "")
        )
        price_cands = candidates[has_price]
        if price_cands.empty:
            return None, None, None

        if len(price_cands) == 1 or not consommable_name:
            row = price_cands.iloc[0]
            return (
                float(row[self.PRIX_UNITAIRE_COL]),
                str(row[self.CONSOMMABLE_COL]),
                str(row[self.CONDT_IJM_COL]),
            )

        # Fuzzy match sur Consommable
        name_lower = consommable_name.lower()
        best_score = -1.0
        best_row = price_cands.iloc[0]
        for _, row in price_cands.iterrows():
            score = SequenceMatcher(
                None, name_lower, str(row[self.CONSOMMABLE_COL]).lower()
            ).ratio()
            if score > best_score:
                best_score = score
                best_row = row

        return (
            float(best_row[self.PRIX_UNITAIRE_COL]),
            str(best_row[self.CONSOMMABLE_COL]),
            str(best_row[self.CONDT_IJM_COL]),
        )

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