# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# windows/carbon_calculator.py

import math
import pandas as pd
from PySide6.QtWidgets import QMessageBox
from ui.data_manager import DataManager
from ui.display_utils import clean_text, normalize_nacres_prefix

class CarbonCalculator:
    """
    Classe pour calculer le bilan carbone via un DataManager.
    """

    def __init__(self, data_manager: DataManager):
        self.dm = data_manager

    @property
    def data(self):
        return self.dm.get_main_data()

    @property
    def data_masse(self):
        return self.dm.get_data_masse()

    @property
    def data_materials(self):
        return self.dm.get_data_materials()

    def compute_emission_data(self, data_dict):
        """
        Calcule les émissions carbone (prix + incertitude) et (masse NACRES + incertitude),
        en évitant KeyError sur l'index de la Série quand on récupère l'incertitude.
        """
        category   = data_dict.get('category', '')
        subcat     = data_dict.get('subcategory', '')
        subsub     = data_dict.get('subsubcategory', '')
        name       = data_dict.get('name', '')
        year       = data_dict.get('year', '')

        val = float(data_dict.get('value', 0.0))  # ex. km/jour ou euros ou litres
        days           = int(data_dict.get('days', 1))

        code_nacres    = data_dict.get('code_nacres', 'NA')
        consommable    = data_dict.get('consommable', 'NA')
        quantity       = float(data_dict.get('quantity', 0) or 0.0)
        
        # Valeurs de sortie par défaut
        ep = 0.0
        ep_err = 0.0
        em = 0.0
        em_err = 0.0
        tm = 0.0
        error_message = None

        # Cas spécial : Machine
        if category == 'Machine':
            # Récupérer le facteur d'émission et son incertitude
            emission_factor = 0.0
            factor_uncert = 0.0
            mask = (self.data['category'] == 'Électricité') & (self.data['name'] == data_dict.get('electricity_type', ''))
            filtered_data = self.data[mask]
            if filtered_data.empty:
                error_message = "Impossible de trouver le facteur d'émission pour ce type d'électricité."
                return (0.0, 0.0, 0.0, 0.0, 0.0, error_message)
            emission_factor = float(filtered_data['total'].iloc[0])
            if 'uncertainty' in filtered_data.columns:
                factor_uncert_value = filtered_data['uncertainty'].iloc[0]
                factor_uncert = float(factor_uncert_value or 0.0)

            # Calcul des émissions et de l'incertitude
            emissions = val * emission_factor
            emissions_error = emissions * factor_uncert

            ep = emissions
            ep_err = emissions_error

            return (ep, ep_err, em, em_err, tm, error_message)

        # Logique pour Véhicules (on multiplie par days)
        if category == 'Véhicules':
            total_value = val * days
        else:
            # Achats, Activités, etc. => on suppose data_dict['value'] = la valeur totale
            total_value = val

        # Filtrer self.data pour trouver le facteur d’émission
        mask = (
            (self.data['category'] == category) &
            (self.data['subcategory'] == subcat) &
            (self.data['subsubcategory'].fillna('') == subsub) &
            (self.data['name'].fillna('') == name)
        )
        if year:
            mask &= (self.data['year'].astype(str) == str(year))

        filtered = self.data[mask]
        if filtered.empty:
            # Fallback: comparaison insensible à la casse / aux espaces
            def _norm_series(series):
                return series.fillna('').astype(str).str.strip().str.casefold()

            norm_category = str(category).strip().casefold()
            norm_subcat = str(subcat).strip().casefold()
            norm_subsub = str(subsub).strip().casefold()
            norm_name = str(name).strip().casefold()

            mask_norm = (
                (_norm_series(self.data['category']) == norm_category) &
                (_norm_series(self.data['subcategory']) == norm_subcat) &
                (_norm_series(self.data['subsubcategory']) == norm_subsub) &
                (_norm_series(self.data['name']) == norm_name)
            )
            if year:
                mask_norm &= (self.data['year'].astype(str) == str(year))
            filtered = self.data[mask_norm]

        if filtered.empty:
            error_message = "Aucune donnée disponible pour cette sélection."
            return (0.0, 0.0, 0.0, 0.0, 0.0, error_message)

        # Récupérer le facteur d'émission "total"
        emission_factor = float(filtered['total'].iloc[0])

        # Récupérer l'incertitude (évite KeyError en utilisant .iloc[0])
        factor_uncert = 0.0
        if 'uncertainty' in filtered.columns:
            # c'est une Série, on prend la 1ère ligne
            factor_uncert_value = filtered['uncertainty'].iloc[0]
            factor_uncert = float(factor_uncert_value or 0.0)

        # Calcul prix
        ep = total_value * emission_factor
        ep_err = ep * factor_uncert

        # Cas spécial pour Achats + code NACRES : distinction liquides vs solides
        if category == 'Achats' and code_nacres != 'NA':
            origine = data_dict.get('origine', self.dm.TRANSPORT_DEFAULT)
            transport_factor, transport_uncert = self.dm.get_transport_factor(origine)
            custom_fe = float(data_dict.get('custom_fe', 0.0) or 0.0)

            # 1) On regarde si c'est un liquide
            liq_row = self.dm.get_liquid_data(code_nacres, consommable)
            if liq_row is not None:
                e_liq, m_liq, err_liq = self._calculate_liquid_emissions(code_nacres, quantity, consommable)
                # Facteur personnalisé (kg eCO₂/L) si aucun facteur en base
                if e_liq == 0.0 and custom_fe > 0.0:
                    e_liq = (quantity / 1000.0) * custom_fe
                    err_liq = 0.0
                    # Masse pour transport : densité si dispo, sinon 1 g/mL
                    dens = float(liq_row.get("Densité (g/mL)", 0.0) or 0.0)
                    m_liq = (dens if dens > 0 else 1.0) * quantity / 1000.0

                # Émissions du contenant et de l'emballage (proratées au volume utilisé)
                vol_flacon = float(liq_row.get("Volume flacon (mL)", 0.0) or 0.0)
                if vol_flacon > 0:
                    fraction = quantity / vol_flacon
                    for col_mat, col_masse in (
                        ("Matériau contenant", "Masse contenant (g)"),
                        ("Matériau emballage", "Masse emballage (g)"),
                    ):
                        mat = str(liq_row.get(col_mat, "") or "").strip()
                        masse_g = float(liq_row.get(col_masse, 0.0) or 0.0)
                        if mat and masse_g > 0:
                            co2_mat, _ = self.dm.get_material_data(mat)
                            if co2_mat:
                                e_liq += fraction * (masse_g / 1000.0) * co2_mat

                transport_em = m_liq * transport_factor
                transport_err = transport_em * transport_uncert
                em     = e_liq + transport_em
                em_err = (err_liq ** 2 + transport_err ** 2) ** 0.5
                tm     = m_liq
            else:
                # 2) Calcul classique pour consommables solides
                e_mass, t_mass, e_mass_err, missing_mats = self._calculate_mass_based_emissions_old(
                    code_nacres, consommable, quantity
                )
                # Facteur personnalisé (kg eCO₂/kg) pour produits vrac sans matériau défini
                if e_mass == 0.0 and custom_fe > 0.0:
                    masse_unitaire_g = float(data_dict.get('masse_unitaire', 0.0) or 0.0)
                    if masse_unitaire_g > 0.0:
                        mass_kg = quantity * masse_unitaire_g / 1000.0
                        e_mass = mass_kg * custom_fe
                        t_mass = mass_kg
                        e_mass_err = 0.0
                transport_em = t_mass * transport_factor
                transport_err = transport_em * transport_uncert
                em     = e_mass + transport_em
                em_err = (e_mass_err ** 2 + transport_err ** 2) ** 0.5
                tm     = t_mass
                if missing_mats:
                    noms = ", ".join(missing_mats)
                    QMessageBox.warning(
                        None,
                        "Matériaux non trouvés",
                        f"Les matériaux suivants sont absents de la base de données "
                        f"et n'ont pas été comptabilisés dans le calcul :\n\n{noms}\n\n"
                        f"Vérifiez la base « empreinte_carbone_materiaux »."
                    )

        return (ep, ep_err, em, em_err, tm, error_message)

    def _calculate_mass_based_emissions_old(self, code_nacres, consommable, quantity):
        """
        Calcule l'empreinte carbone totale (produit + emballage + conditionnement)
        à partir des masses unitaires et des matériaux.
        """
        # 1) Cas où aucun code NACRES valide n'est fourni
        if not code_nacres or code_nacres == 'NA':
            return (0.0, 0.0, 0.0, [])

        # 2) Récupérer la ligne correspondante dans data_masse
        code_series = self.data_masse[self.dm.CODE_NACRES_COL]
        if hasattr(self.dm, "nacres_code_mask") and callable(self.dm.nacres_code_mask):
            code_mask = self.dm.nacres_code_mask(code_series, code_nacres)
        else:
            code_clean = clean_text(code_nacres).upper()
            prefix = normalize_nacres_prefix(code_clean)
            clean_series = code_series.fillna("").astype(str).str.strip().str.upper()
            code_mask = (clean_series == code_clean) | (clean_series.str[:4] == prefix)

        df_row = self.data_masse[
            code_mask &
            (self.data_masse[self.dm.CONSOMMABLE_COL].astype(str).str.strip() == consommable.strip())
        ]
        if df_row.empty:
            return (0.0, 0.0, 0.0, [])
        row = df_row.iloc[0]

        # 3) Définir les composants à traiter, y compris le second matériau du produit
        composants = [
            # Produit principal : matériau 1 puis matériau 2
            (self.dm.MASSE_G_COL,  self.dm.MATERIAU_COL),
            (getattr(self.dm, "MASSE_G2_COL", None), getattr(self.dm, "MATERIAU2_COL", None)),
            (getattr(self.dm, "MASSE_G3_COL", None), getattr(self.dm, "MATERIAU3_COL", None)),
            # Emballage
            (self.dm.MASSE_EMBALLAGE_COL, self.dm.MATERIAU_EMBALLAGE_COL),
            # Conditionnement
            (self.dm.MASSE_CONDITIONNEMENT_COL, self.dm.MATERIAU_CONDITIONNEMENT_COL),
        ]

        total_mass_kg = 0.0
        total_emission = 0.0
        total_unc_sq = 0.0
        missing_materials = []

        # 4) Pour chaque composant, calculer sa contribution
        for col_masse, col_mat in composants:
            if col_masse is None or col_mat is None:
                continue
            # Lecture brute de la masse (g) — NaN doit être traité comme 0
            _raw = row.get(col_masse, 0.0)
            raw_masse = 0.0 if pd.isna(_raw) else float(_raw)
            # Si on est dans le conditionnement, on divise par le nombre par conditionnement
            if col_masse == self.dm.MASSE_CONDITIONNEMENT_COL:
                nombre = row.get(self.dm.NOMBRE_PAR_COND_COL, 1) or 1
                if nombre <= 0:
                    continue
                raw_masse = raw_masse / float(nombre)
            # On obtient la masse finale du composant
            masse_g = raw_masse
            materiau = row.get(col_mat, "") or ""

            # Ignorer si pas de masse ou matériau manquant
            if masse_g <= 0 or not materiau:
                continue

            # Récupérer le facteur CO₂ (kgCO₂/kg) et son incertitude
            # AVANT d’accumuler la masse, pour ne pas compter une masse sans émission
            co2_per_kg, uncert_mat = self.dm.get_material_data(materiau)
            if co2_per_kg is None:
                missing_materials.append(materiau)
                continue

            # Conversion en kg et application de la quantité
            masse_kg = quantity * masse_g / 1000.0
            total_mass_kg += masse_kg

            # Calcul de l’émission pour ce composant
            emission = masse_kg * co2_per_kg
            total_emission += emission

            # Accumuler l’incertitude (émission * taux d’incertitude)²
            total_unc_sq += (emission * uncert_mat) ** 2

        total_unc = total_unc_sq ** 0.5
        return (total_emission, total_mass_kg, total_unc, missing_materials)
    

    def _calculate_liquid_emissions(self, code_nacres, volume_ml, consommable=None):
        """
        Calcule l'empreinte carbone d'un consommable liquide via volume (mL).
        """
        row = self.dm.get_liquid_data(code_nacres, consommable)
        if row is None:
            return (0.0, 0.0, 0.0)

        # Colonnes de la table liquid
        dens = float(row.get("Densité (g/mL)", 0.0) or 0.0)
        conc = float(row.get("Concentration (mg/mL)", 0.0) or 0.0)
        factor = float(row.get("Facteur CO₂ (kg CO₂e/kg)", 0.0) or 0.0)
        uncert_pct = float(row.get("Incertitude (%)", 0.0) or 0.0) / 100.0

        # volume (mL) → masse (kg)
        # Si densité disponible : masse = volume × densité / 1000
        # Sinon si concentration (mg/mL) : masse = volume × concentration (mg) / 1 000 000
        if dens > 0:
            mass_kg = dens * volume_ml / 1000.0
        elif conc > 0:
            mass_kg = volume_ml * conc / 1_000_000.0
        else:
            mass_kg = 0.0

        # émission + incertitude
        emission = mass_kg * factor
        error = emission * uncert_pct

        return (emission, mass_kg, error)
