# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# windows/carbon_calculator.py

import math
import pandas as pd
from PySide6.QtWidgets import QMessageBox
from windows.data_manager import DataManager

class CarbonCalculator:
    """
    Classe pour calculer le bilan carbone via un DataManager.
    """

    def __init__(self, data_manager: DataManager):
        self.dm = data_manager
        self.data = self.dm.get_main_data()
        self.data_masse = self.dm.get_data_masse()
        self.data_materials = self.dm.get_data_materials()

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
        quantity       = int(data_dict.get('quantity', 0))
        
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

        # Calcul massique NACRES si Achats + code_nacres != 'NA'
        if category == 'Achats' and code_nacres != 'NA':
            e_mass, t_mass, e_mass_err = self._calculate_mass_based_emissions_old(
                code_nacres, consommable, quantity
            )
            em = e_mass
            em_err = e_mass_err
            tm = t_mass

        return (ep, ep_err, em, em_err, tm, error_message)

    def _calculate_mass_based_emissions_old(self, code_nacres, consommable, quantity):
        """
        Calcule les émissions massiques en matching sur (Code NACRES, Consommable)
        dans data_masse, puis cherche le matériau dans data_materials.
        """
        if not code_nacres or code_nacres == 'NA':
            return (0.0, 0.0, 0.0)

        matching = self.data_masse[
            (self.data_masse['Code NACRES'].str.strip() == code_nacres.strip()) &
            (self.data_masse['Consommable'].str.strip() == consommable.strip())
        ]
        if matching.empty:
            return (0.0, 0.0, 0.0)

        row = matching.iloc[0]
        masse_g = row.get("Masse unitaire (g)", 0.0)
        materiau = row.get("Matériau", "")
        incert_mass_factor = float(row.get("uncertainty", 0.0) or 0.0)

        masse_kg_unitaire = float(masse_g) / 1000.0
        masse_totale_kg = masse_kg_unitaire * quantity

        mat_filter = self.data_materials[self.data_materials['Materiau'] == materiau]
        if mat_filter.empty:
            return (0.0, masse_totale_kg, 0.0)

        eCO2_par_kg = float(mat_filter.iloc[0].get("Equivalent CO₂ (kg eCO₂/kg)", 0.0))
        incert_material = float(mat_filter.iloc[0].get("uncertainty", 0.0) or 0.0)

        eCO2_total = masse_totale_kg * eCO2_par_kg
        incert_total_fraction = (incert_mass_factor**2 + incert_material**2)**0.5
        eCO2_total_error = eCO2_total * incert_total_fraction

        return (eCO2_total, masse_totale_kg, eCO2_total_error)
