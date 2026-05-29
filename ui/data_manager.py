# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# windows/data_manager.py

import os
import pandas as pd
from ui.display_utils import (
    clean_text,
    looks_like_liquid_commercial_product,
    normalize_nacres_prefix,
)

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
    MASSE_G3_COL      = "Masse unitaire troisième materiaux (g)"
    MATERIAU3_COL     = "Matériau troisième materiaux"
    MASSE_EMBALLAGE_COL = "Masse emballage unitaire (g)"
    MATERIAU_EMBALLAGE_COL = "Matériau emballage"
    NOMBRE_PAR_EMBALLAGE_COL = "Nbr par emballage secondaire"
    MASSE_CONDITIONNEMENT_COL = "Masse condionnement (g)"
    MATERIAU_CONDITIONNEMENT_COL = "Matériau conditionnement"
    NOMBRE_PAR_COND_COL = "Nbr par conditionnement"

    # Spécifique matériaux
    MATERIAU_NAME_COL = "Materiau"
    EQUIV_CO2_COL = "Equivalent CO₂ (kg eCO₂/kg)"
    EQUIV_CO2_EOL_COL = "EoL Facteur CO₂ (kg eCO₂/kg)"
    UNCERTAINTY_EOL_COL = "EoL Incertitude"
    EOL_FACTOR_NAME_COL = "EoL Nom facteur"
    EOL_LIST_NAME_COL = "Nom"
    EOL_LIST_FACTOR_COL = "Facteur CO₂ (kg eCO₂/kg)"
    EOL_LIST_UNCERTAINTY_COL = "Incertitude"

    # Colonnes prix consommables. "Prix du conditionnement" est la source de
    # vérité; les anciennes colonnes *_ijm restent lues en fallback pour les
    # bases non migrées.
    PRIX_CONDITIONNEMENT_COL = "Prix du conditionnement"
    SOURCE_CATALOGUE_IJM_COL = "Source catalogue IJM"
    UNITE_LIQUIDE_COL = "Unité liquide"
    VOLUME_FLACON_COL = "Volume flacon (mL)"
    FACTEUR_LIQUIDE_SOURCE_COL = "Facteur liquide source"
    PRIX_UNITAIRE_COL = "prix_unitaire_ijm"
    PRIX_HT_COL       = "prix_ht_ijm"
    CONDT_IJM_COL     = "condt_ijm"
    NB_UNITES_IJM_COL = "nb_unites_ijm"
    DESIGNATION_IJM_COL = "designation_ijm"
    CODE_IJM_COL = "code_ijm"
    MARQUE_IJM_COL = "marque_ijm"
    SCORE_MATCH_COL = "score_match"
    VALIDATION_STATUS_COL = "Statut validation"
    VALIDATION_NATURE_COL = "Nature validation"

    SQLITE_ENV_VAR = "LABECO2_SQLITE_PATH"
    TRANSPORT_ORIGINE_COL = "Origine"
    TRANSPORT_FACTOR_COL = "Facteur transport (kg CO₂e/kg)"
    TRANSPORT_UNCERT_COL = "Incertitude"
    TRANSPORT_DEFAULT = "Inconnue (défaut)"


    def __init__(self, base_path, user_path=None, sqlite_path=None):
        """
        :param base_path: Répertoire des données en lecture seule (bundlées).
        :param user_path: Répertoire des données modifiables (persistant).
                          Si None, identique à base_path (mode développement).
        :param sqlite_path: Base SQLite à lire.
        """
        self.base_path = base_path
        self.user_path = user_path if user_path is not None else base_path
        self.sqlite_path = (
            sqlite_path
            if sqlite_path is not None else
            os.environ.get(self.SQLITE_ENV_VAR)
        )
        if not self.sqlite_path:
            raise ValueError("DataManager nécessite un chemin SQLite.")
        self._load_from_sqlite(self.sqlite_path)

        # Charger les prix du catalogue IJM (optionnel)
        self.data_prix_ijm = self._load_prix_ijm()

    def _load_from_sqlite(self, sqlite_path):
        from ui.sqlite_legacy_adapter import load_legacy_dataframes

        frames = load_legacy_dataframes(sqlite_path)
        self.main_data = frames["main_data"]
        self.data_masse = frames["data_masse"]
        self.data_materials = frames["data_materials"]
        self.data_liquides = frames["data_liquides"]
        self.data_transport = frames["data_transport"]
        self.data_eol_factors = frames.get("data_eol_factors")
        if self.data_eol_factors is None:
            import pandas as pd
            self.data_eol_factors = pd.DataFrame(columns=["Nom", "Facteur CO₂ (kg eCO₂/kg)", "Incertitude", "Source"])

    def reload(self):
        """Recharge les DataFrames depuis la base SQLite active."""
        if not self.sqlite_path:
            raise ValueError("Aucune base SQLite active pour recharger les données.")
        self._load_from_sqlite(self.sqlite_path)
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

    def get_material_eol_data(self, material_name):
        """Retourne (co2_par_kg_eol, incert_eol, eol_factor_name) pour un matériau.

        Renvoie (None, None, None) si le matériau n'a pas de mapping EoL (par
        exemple : métaux récupérés en mâchefers, sans facteur EoL associé).
        Le calculateur doit alors ignorer la contribution EoL de ce composant.
        """
        import pandas as pd

        if pd.isna(material_name) or not isinstance(material_name, str):
            return None, None, None

        df_mat = self.data_materials
        if self.EQUIV_CO2_EOL_COL not in df_mat.columns:
            return None, None, None

        mask = df_mat[self.MATERIAU_NAME_COL].astype(str).str.strip() == material_name.strip()
        filtered = df_mat[mask]
        if filtered.empty:
            return None, None, None

        raw_co2 = filtered[self.EQUIV_CO2_EOL_COL].iloc[0]
        if pd.isna(raw_co2):
            return None, None, None
        co2_eol = float(raw_co2)

        raw_unc = filtered[self.UNCERTAINTY_EOL_COL].iloc[0] if self.UNCERTAINTY_EOL_COL in filtered.columns else None
        incert_eol = 0.0 if (raw_unc is None or pd.isna(raw_unc)) else float(raw_unc)

        raw_name = filtered[self.EOL_FACTOR_NAME_COL].iloc[0] if self.EOL_FACTOR_NAME_COL in filtered.columns else ""
        factor_name = "" if pd.isna(raw_name) else str(raw_name).strip()

        return co2_eol, incert_eol, factor_name

    def get_eol_factor_by_name(self, factor_name):
        """Retourne (co2_par_kg, incertitude) pour un facteur EoL donné par son nom.

        Utilisé par le calculateur pour résoudre les facteurs filière (DASRI / DIS)
        à partir du nom retourné par ui.end_of_life.factor_name_for_nacres().
        Renvoie (None, None) si le facteur n'existe pas.
        """
        import pandas as pd

        if not factor_name:
            return None, None

        df = self.data_eol_factors
        if df is None or df.empty:
            return None, None

        mask = df[self.EOL_LIST_NAME_COL].astype(str).str.strip() == str(factor_name).strip()
        filtered = df[mask]
        if filtered.empty:
            return None, None

        raw_co2 = filtered[self.EOL_LIST_FACTOR_COL].iloc[0]
        co2 = 0.0 if pd.isna(raw_co2) else float(raw_co2)
        raw_unc = filtered[self.EOL_LIST_UNCERTAINTY_COL].iloc[0]
        unc = 0.0 if pd.isna(raw_unc) else float(raw_unc)
        return co2, unc

    def get_filiere_factor(self, code_nacres):
        """Retourne (co2_par_kg, incertitude, filiere) pour le facteur filière (DASRI ou
        DIS) à appliquer au consommable, déterminé à partir du code NACRES.

        La filière est résolue via ui.end_of_life ; si le facteur correspondant
        n'est pas trouvé en base, renvoie (None, None, filiere).
        """
        from ui.end_of_life import filiere_for_nacres, factor_name_for_nacres
        filiere = filiere_for_nacres(code_nacres)
        factor_name = factor_name_for_nacres(code_nacres)
        co2, unc = self.get_eol_factor_by_name(factor_name)
        return co2, unc, filiere

    def get_data_liquides(self):
        """Retourne la DataFrame des consommables liquides."""
        return self.data_liquides

    def nacres_code_mask(self, series, code_nacres):
        """
        Masque robuste pour comparer des codes NACRES courts ou longs.

        La base peut contenir seulement le code court ("NB13") ou un libellé complet
        ("NB13 Culture cellulaire..."). On compare d'abord la chaîne complète, puis
        le préfixe NACRES.
        """
        code_clean = clean_text(code_nacres).upper()
        if not code_clean:
            return pd.Series(False, index=series.index)

        clean_series = series.fillna("").astype(str).str.strip().str.upper()
        mask = clean_series == code_clean
        prefix = normalize_nacres_prefix(code_clean)
        if prefix:
            mask |= clean_series.str[:4] == prefix
        return mask

    def get_transport_origins(self):
        """Retourne la liste ordonnée des origines géographiques disponibles."""
        if self.data_transport.empty:
            return [self.TRANSPORT_DEFAULT]
        return self.data_transport[self.TRANSPORT_ORIGINE_COL].tolist()

    def get_transport_factor(self, origine):
        """
        Retourne (facteur_kg_co2_par_kg, incertitude) pour une origine donnée.
        Utilise la ligne 'Inconnue (défaut)' si l'origine est absente.
        """
        if self.data_transport.empty:
            return (0.265, 0.30)
        df = self.data_transport
        mask = df[self.TRANSPORT_ORIGINE_COL] == origine
        if not mask.any():
            mask = df[self.TRANSPORT_ORIGINE_COL] == self.TRANSPORT_DEFAULT
        if not mask.any():
            return (0.265, 0.30)
        row = df[mask].iloc[0]
        return (float(row[self.TRANSPORT_FACTOR_COL]), float(row[self.TRANSPORT_UNCERT_COL]))

    def _load_prix_ijm(self):
        """
        Charge le CSV des prix du catalogue IJM.
        Cherche dans Scrapping/output/ (dev) puis data_prix/ (production).
        Retourne un DataFrame vide si absent.
        """
        candidates = [
            os.path.join(self.base_path, "tools", "migration", "scraping", "output", "prix_ijm_2025.csv"),
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

    @staticmethod
    def _clean_cell(value):
        """Retourne une chaîne propre pour une cellule pandas possiblement vide."""
        if pd.isna(value):
            return ""
        text = str(value).strip()
        return "" if text.lower() in ("", "nan", "none", "n/a") else text

    @staticmethod
    def _to_float_or_none(value):
        if pd.isna(value):
            return None
        text = str(value).strip().replace(",", ".")
        if text.lower() in ("", "nan", "none", "n/a"):
            return None
        try:
            return float(text)
        except (TypeError, ValueError):
            return None

    def _row_price_conditionnement(self, row):
        """Prix HT du conditionnement, avec fallback legacy prix_ht_ijm."""
        price = self._to_float_or_none(row.get(self.PRIX_CONDITIONNEMENT_COL, None))
        if price is None:
            price = self._to_float_or_none(row.get(self.PRIX_HT_COL, None))
        return price

    def _row_nb_conditionnement(self, row):
        """Nombre d'unités par conditionnement, avec fallback legacy nb_unites_ijm."""
        nb = self._to_float_or_none(row.get(self.NOMBRE_PAR_COND_COL, None))
        if nb is None:
            nb = self._to_float_or_none(row.get(self.NB_UNITES_IJM_COL, None))
        return nb

    def _row_prix_unitaire(self, row):
        price = self._row_price_conditionnement(row)
        nb = self._row_nb_conditionnement(row)
        if price is not None and nb and nb > 0:
            return price / nb
        return self._to_float_or_none(row.get(self.PRIX_UNITAIRE_COL, None))

    def _row_has_price(self, row):
        return self._row_prix_unitaire(row) is not None

    def _prix_info_from_row(self, row):
        """Construit les métadonnées de prix d'une ligne consommable."""
        def get(col_name):
            return self._clean_cell(row.get(col_name, ""))

        def validation_label():
            status_labels = {
                "validated": "Validé",
                "draft": "Draft",
                "deprecated": "Déprécié",
            }
            raw_status = get(self.VALIDATION_STATUS_COL)
            nature = get(self.VALIDATION_NATURE_COL)
            if not raw_status and not nature:
                return ""
            status = status_labels.get(raw_status.casefold(), raw_status)
            return " - ".join(part for part in (status, nature.lower() if nature else "") if part)

        prix_conditionnement = self._row_price_conditionnement(row)
        nb_unites = self._row_nb_conditionnement(row)
        prix_unitaire = self._row_prix_unitaire(row)

        return {
            "prix_unitaire": prix_unitaire,
            "consommable": get(self.CONSOMMABLE_COL),
            "designation": get(self.DESIGNATION_IJM_COL) or get(self.CONSOMMABLE_COL),
            "conditionnement": get(self.CONDT_IJM_COL),
            "nb_unites": "" if nb_unites is None else nb_unites,
            "prix_ht": "" if prix_conditionnement is None else prix_conditionnement,
            "code_ijm": get(self.CODE_IJM_COL),
            "marque": get(self.MARQUE_IJM_COL),
            "score_match": get(self.SCORE_MATCH_COL),
            "source_catalogue": get(self.SOURCE_CATALOGUE_IJM_COL),
            "validation": validation_label(),
        }

    def _row_packaging_label(self, row) -> str:
        return self._clean_cell(row.get(self.CONDT_IJM_COL, ""))

    def _filter_rows_by_packaging(self, rows, packaging):
        pack = clean_text(packaging)
        if not pack or rows.empty:
            return rows
        if self.CONDT_IJM_COL not in rows.columns:
            return rows
        exact_pack = rows[
            rows[self.CONDT_IJM_COL].fillna("").astype(str).str.strip() == pack
        ]
        return exact_pack if not exact_pack.empty else rows

    def _find_prix_unitaire_row(self, code_nacres, consommable_name="", packaging=""):
        """
        Retourne la ligne data_masse contenant le prix IJM le plus pertinent.
        Retourne None si aucun prix disponible.
        """
        from difflib import SequenceMatcher

        code = clean_text(code_nacres).upper()
        df = self.data_masse
        if self.PRIX_CONDITIONNEMENT_COL not in df.columns and self.PRIX_UNITAIRE_COL not in df.columns:
            return None

        mask = self.nacres_code_mask(df[self.CODE_NACRES_COL], code)
        candidates = df[mask]

        if candidates.empty:
            return None

        if consommable_name:
            exact = candidates[
                candidates[self.CONSOMMABLE_COL].astype(str).str.strip() == consommable_name.strip()
            ]
            exact = self._filter_rows_by_packaging(exact, packaging)
            if not exact.empty:
                for _, row in exact.iterrows():
                    if self._row_has_price(row):
                        return row
                return None

        # Garder seulement les lignes avec un prix
        has_price = candidates.apply(self._row_has_price, axis=1)
        price_cands = candidates[has_price]
        price_cands = self._filter_rows_by_packaging(price_cands, packaging)
        if price_cands.empty:
            return None

        if len(price_cands) == 1 or not consommable_name:
            return price_cands.iloc[0]

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

        return best_row

    def get_prix_unitaire_info(self, code_nacres, consommable_name="", packaging=""):
        """
        Retourne les métadonnées du produit IJM utilisé pour le prix unitaire.
        Retourne None si aucun prix disponible.
        """
        row = self._find_prix_unitaire_row(code_nacres, consommable_name, packaging)
        if row is None:
            return None
        return self._prix_info_from_row(row)

    def get_prix_unitaire(self, code_nacres, consommable_name="", packaging=""):
        """
        Retourne (prix_unitaire, designation, condt) depuis data_masse.
        Recherche par Code NACRES (4 chars) puis fuzzy match sur le nom.
        Retourne (None, None, None) si aucun prix disponible.
        """
        info = self.get_prix_unitaire_info(code_nacres, consommable_name, packaging)
        if not info:
            return None, None, None

        return (
            info["prix_unitaire"],
            info["designation"],
            info["conditionnement"],
        )

    def get_liquid_data(self, code_nacres, produit=None, packaging=""):
        """
        Cherche un consommable liquide par code NACRES.
        Retourne la Series de la ligne si trouvée, sinon None.
        """
        if self.data_liquides.empty:
            return None
        df = self.data_liquides
        mask = self.nacres_code_mask(df[self.CODE_NACRES_COL], code_nacres)
        produit_clean = clean_text(produit)
        if produit_clean and "Produit" in df.columns:
            mask &= df["Produit"].astype(str).str.strip() == produit_clean
        filtered = df[mask]
        filtered = self._filter_rows_by_packaging(filtered, packaging)
        return filtered.iloc[0] if not filtered.empty else None

    def get_consumable_row(self, code_nacres, consommable_name, packaging=""):
        if self.data_masse.empty:
            return None
        df = self.data_masse
        mask = (
            self.nacres_code_mask(df[self.CODE_NACRES_COL], code_nacres) &
            (df[self.CONSOMMABLE_COL].astype(str).str.strip() == clean_text(consommable_name))
        )
        rows = df[mask]
        rows = self._filter_rows_by_packaging(rows, packaging)
        return rows.iloc[0] if not rows.empty else None

    def get_consumable_liquid_factor_data(self, code_nacres, consommable_name, packaging=""):
        """
        Retourne (ligne consommable, ligne facteur liquide) pour un produit
        commercial stocké dans la base consommables mais lié à un facteur de
        la base Liquides & Solvants.

        Résolution principale par emission_factor_id (stable au renommage),
        puis fallback par nom texte si l'identifiant est absent.
        """
        product_row = self.get_consumable_row(code_nacres, consommable_name, packaging)
        if product_row is None:
            return None, None

        # Résolution par ID (SQLite) — insensible aux renommages
        factor_id = self._clean_cell(product_row.get("emission_factor_id", ""))
        if factor_id:
            df_liq = self.data_liquides
            if "factor_id" in df_liq.columns:
                match = df_liq[df_liq["factor_id"].astype(str) == factor_id]
                if not match.empty:
                    return product_row, match.iloc[0]

        # Fallback par nom texte si factor_id est absent.
        factor_name = self._clean_cell(product_row.get(self.FACTEUR_LIQUIDE_SOURCE_COL, ""))
        if not factor_name:
            return product_row, None
        factor_row = self.get_liquid_data(code_nacres, factor_name)
        return product_row, factor_row

    def is_liquid_commercial_row(self, row):
        return looks_like_liquid_commercial_product(
            row,
            factor_col=self.FACTEUR_LIQUIDE_SOURCE_COL,
            unit_col=self.UNITE_LIQUIDE_COL,
            volume_col=self.VOLUME_FLACON_COL,
            name_col=self.CONSOMMABLE_COL,
            code_col=self.CODE_NACRES_COL,
        )
