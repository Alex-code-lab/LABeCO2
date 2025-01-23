# windows/carbon_calculator.py

import math
from windows.data_manager import DataManager

class CarbonCalculator:
    """
    Classe pour calculer les émissions carbone (prix & masse) en utilisant DataManager.
    """

    def __init__(self, data_manager: DataManager):
        """
        :param data_manager: instance de DataManager
        """
        self.dm = data_manager

    def calculate_price_based_emissions(self, category, subcategory, subsub, name, year, value, days=1):
        """
        Calcule les émissions par le "prix" (ou la "valeur").
        Retourne (emissions_price, emissions_price_error, msg_error).
        """
        total_value = value * days
        emission_factor, factor_uncert = self.dm.get_emission_factor(
            category, subcategory, subsub, name, year
        )
        if emission_factor is None:
            return (0.0, 0.0, "Aucune donnée (price-based).")

        ep = total_value * emission_factor
        ep_err = ep * factor_uncert
        return (ep, ep_err, None)

    def calculate_mass_based_emissions(self, code_nacres, quantity=0):
        """
        Calcule les émissions basées sur la masse (NACRES + quantité).
        Retourne (eCO2_total, total_mass, eCO2_total_error).
        """
        if not code_nacres or code_nacres == 'NA':
            return (0.0, 0.0, 0.0)

        data_masse = self.dm.get_data_masse()
        matching = data_masse[data_masse[self.dm.CODE_NACRES_COL].str.strip() == code_nacres.strip()]
        if matching.empty:
            return (0.0, 0.0, 0.0)

        row = matching.iloc[0]
        masse_g = row.get(self.dm.MASSE_G_COL, 0.0)
        materiau = row.get(self.dm.MATERIAU_COL, "")
        incert_mass_factor = row.get(self.dm.UNCERTAINTY_COL, 0.0)

        masse_kg_unitaire = float(masse_g) / 1000.0
        masse_totale_kg = masse_kg_unitaire * quantity

        co2_par_kg, incert_material = self.dm.get_material_data(materiau)
        if co2_par_kg is None:
            return (0.0, masse_totale_kg, 0.0)

        eCO2_total = masse_totale_kg * co2_par_kg
        incert_total_fraction = (incert_mass_factor**2 + incert_material**2)**0.5
        eCO2_total_error = eCO2_total * incert_total_fraction

        return (eCO2_total, masse_totale_kg, eCO2_total_error)

    def recalculate_emissions(self, data_dict):
        """
        Recalcule les émissions globales (prix + masse), renvoie :
          (ep, ep_err, em, em_err, total_mass, msg_price)
        """
        category = data_dict.get('category', '')
        subcat   = data_dict.get('subcategory', '')
        subsub   = data_dict.get('subsubcategory', '')
        name     = data_dict.get('name', '')
        year     = data_dict.get('year', '')
        value    = float(data_dict.get('value', 0.0))
        days     = int(data_dict.get('days', 1))
        code_nac = data_dict.get('code_nacres', 'NA')
        quantity = int(data_dict.get('quantity', 0))

        # Par défaut
        emission_mass = 0.0
        emission_mass_error = 0.0
        total_mass = 0.0

        # Machine => pas de calcul
        if category == 'Machine':
            return (0.0, 0.0, 0.0, 0.0, 0.0, None)

        # 1) Prix
        ep, ep_err, msg_price = self.calculate_price_based_emissions(
            category, subcat, subsub, name, year, value, days
        )

        # 2) Masse si Achats + NACRES != 'NA'
        if category == 'Achats' and code_nac != 'NA':
            # Si code NACRES contient " - ", on ne garde que la 1ere partie
            if " - " in code_nac:
                code_nac = code_nac.split(" - ", 1)[0].strip()
            em, tm, em_err = self.calculate_mass_based_emissions(code_nac, quantity)
            emission_mass = em
            emission_mass_error = em_err
            total_mass = tm

        return (ep, ep_err, emission_mass, emission_mass_error, total_mass, msg_price)

    def calculate_total_emissions_in_history(self, history_items):
        """
        Calcule la somme de l'historique (emissions_price + mass).
        Retourne (total_price, total_price_err, total_mass, total_mass_err).
        """
        total_emissions = 0.0
        total_emissions_error_sq = 0.0
        total_mass_emissions = 0.0
        total_mass_emissions_error_sq = 0.0

        for data in history_items:
            e_price = float(data.get('emissions_price', 0.0))
            e_price_err = float(data.get('emissions_price_error', 0.0))
            total_emissions += e_price
            total_emissions_error_sq += (e_price_err**2)

            e_mass = float(data.get('emission_mass', 0.0))
            e_mass_err = float(data.get('emission_mass_error', 0.0))
            total_mass_emissions += e_mass
            total_mass_emissions_error_sq += (e_mass_err**2)

        tp_err = math.sqrt(total_emissions_error_sq)
        tm_err = math.sqrt(total_mass_emissions_error_sq)
        return (total_emissions, tp_err, total_mass_emissions, tm_err)