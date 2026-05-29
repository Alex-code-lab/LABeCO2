# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# windows/carbon_calculator.py

import math
import pandas as pd
from ui.data_manager import DataManager
from ui.display_utils import clean_text, normalize_nacres_prefix

class CarbonCalculator:
    """
    Classe pour calculer le bilan carbone via un DataManager.
    """

    def __init__(self, data_manager: DataManager):
        self.dm = data_manager
        # Décomposition détaillée du dernier calcul (production / fin de vie par
        # composant). Mis à jour à chaque appel de compute_emission_data ou
        # _calculate_mass_based_emissions_old. Utilisé par l'UI pour afficher
        # le détail au déroulement d'une ligne. None si non-applicable
        # (machine, véhicule, ligne vide).
        self.last_breakdown: dict | None = None

    @staticmethod
    def _safe_float(value, default=0.0):
        """Convertit une cellule numérique en float sans planter sur les champs vides."""
        if value is None:
            return default
        try:
            if pd.isna(value):
                return default
        except (TypeError, ValueError):
            pass
        text = str(value).strip().replace(",", ".")
        if text.casefold() in {"", "nan", "none", "n/a", "nat"}:
            return default
        try:
            return float(text)
        except (TypeError, ValueError):
            return default

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

        Effet de bord : met à jour `self.last_breakdown` avec la décomposition
        détaillée production / fin de vie quand le calcul passe par la voie masse.
        Pour les autres voies (machine, véhicule, liquide), reste None.
        """
        # Reset du breakdown — sera repeuplé seulement si le chemin masse-based est emprunté
        self.last_breakdown = None

        category   = data_dict.get('category', '')
        subcat     = data_dict.get('subcategory', '')
        subsub     = data_dict.get('subsubcategory', '')
        name       = data_dict.get('name', '')
        year       = data_dict.get('year', '')

        val = self._safe_float(data_dict.get('value', 0.0))  # ex. km/jour ou euros ou litres
        days           = int(data_dict.get('days', 1))

        code_nacres    = data_dict.get('code_nacres', 'NA')
        consommable    = data_dict.get('consommable', 'NA')
        conditionnement = clean_text(data_dict.get('conditionnement', ''))
        quantity       = self._safe_float(data_dict.get('quantity', 0), default=0.0)
        
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
            emission_factor = self._safe_float(filtered_data['total'].iloc[0])
            if 'uncertainty' in filtered_data.columns:
                factor_uncert_value = filtered_data['uncertainty'].iloc[0]
                factor_uncert = self._safe_float(factor_uncert_value)

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
        emission_factor = self._safe_float(filtered['total'].iloc[0])

        # Récupérer l'incertitude (évite KeyError en utilisant .iloc[0])
        factor_uncert = 0.0
        if 'uncertainty' in filtered.columns:
            # c'est une Série, on prend la 1ère ligne
            factor_uncert_value = filtered['uncertainty'].iloc[0]
            factor_uncert = self._safe_float(factor_uncert_value)

        # Calcul prix
        ep = total_value * emission_factor
        ep_err = ep * factor_uncert

        # Cas spécial pour Achats + code NACRES : distinction liquides vs solides
        if category == 'Achats' and code_nacres != 'NA':
            origine = data_dict.get('origine', self.dm.TRANSPORT_DEFAULT)
            transport_factor, transport_uncert = self.dm.get_transport_factor(origine)
            custom_fe = self._safe_float(data_dict.get('custom_fe', 0.0))

            # 1) On regarde si c'est un liquide/facteur liquide, soit direct,
            # soit via un produit commercial stocké dans la base consommables.
            product_row, linked_liq_row = (None, None)
            linked_lookup = getattr(self.dm, "get_consumable_liquid_factor_data", None)
            if callable(linked_lookup):
                try:
                    lookup_result = linked_lookup(code_nacres, consommable, conditionnement)
                except TypeError:
                    lookup_result = linked_lookup(code_nacres, consommable)
                if isinstance(lookup_result, tuple) and len(lookup_result) == 2:
                    product_row, linked_liq_row = lookup_result
            try:
                fallback_liq_row = self.dm.get_liquid_data(code_nacres, consommable, conditionnement)
            except TypeError:
                fallback_liq_row = self.dm.get_liquid_data(code_nacres, consommable)
            liq_row = linked_liq_row if linked_liq_row is not None else fallback_liq_row
            if liq_row is not None:
                e_liq, m_liq, err_liq = self._calculate_liquid_emissions_from_row(liq_row, quantity)
                # Facteur personnalisé (kg eCO₂/L) si aucun facteur en base
                if e_liq == 0.0 and custom_fe > 0.0:
                    unit = clean_text(liq_row.get("Unité", "")).casefold()
                    if unit in {"kg", "kilogramme", "kilogrammes"}:
                        e_liq = quantity * custom_fe
                    else:
                        e_liq = (quantity / 1000.0) * custom_fe
                    err_liq = 0.0
                    # Masse pour transport : unité massique si dispo, sinon densité, sinon 1 g/mL.
                    dens = self._safe_float(liq_row.get("Densité (g/mL)", 0.0))
                    if unit in {"kg", "kilogramme", "kilogrammes"}:
                        m_liq = quantity
                    elif unit in {"g", "gramme", "grammes"}:
                        m_liq = quantity / 1000.0
                    else:
                        m_liq = (dens if dens > 0 else 1.0) * quantity / 1000.0

                # Émissions du contenant et de l'emballage (proratées au volume utilisé)
                vol_flacon = self._safe_float(
                    product_row.get(getattr(self.dm, "VOLUME_FLACON_COL", "Volume flacon (mL)"), 0.0)
                    if product_row is not None else
                    liq_row.get("Volume flacon (mL)", 0.0)
                )
                if vol_flacon > 0:
                    fraction = quantity / vol_flacon
                    if product_row is not None:
                        packaging_specs = (
                            (self.dm.MATERIAU_CONDITIONNEMENT_COL, self.dm.MASSE_CONDITIONNEMENT_COL),
                            (self.dm.MATERIAU_EMBALLAGE_COL, self.dm.MASSE_EMBALLAGE_COL),
                        )
                        packaging_row = product_row
                    else:
                        packaging_specs = (
                            ("Matériau contenant", "Masse contenant (g)"),
                            ("Matériau emballage", "Masse emballage (g)"),
                        )
                        packaging_row = liq_row
                    for col_mat, col_masse in packaging_specs:
                        mat = str(packaging_row.get(col_mat, "") or "").strip()
                        masse_g = self._safe_float(packaging_row.get(col_masse, 0.0))
                        if mat and masse_g > 0:
                            co2_mat, _ = self.dm.get_material_data(mat)
                            if co2_mat:
                                e_liq += fraction * (masse_g / 1000.0) * co2_mat

                transport_em = m_liq * transport_factor
                transport_err = transport_em * transport_uncert
                em     = e_liq + transport_em
                em_err = (err_liq ** 2 + transport_err ** 2) ** 0.5
                tm     = m_liq
            elif (
                product_row is not None
                and hasattr(self.dm, "is_liquid_commercial_row")
                and self.dm.is_liquid_commercial_row(product_row)
            ):
                e_liq = (quantity / 1000.0) * custom_fe if custom_fe > 0.0 else 0.0
                err_liq = 0.0
                m_liq = quantity / 1000.0
                transport_em = m_liq * transport_factor
                transport_err = transport_em * transport_uncert
                em = e_liq + transport_em
                em_err = (err_liq ** 2 + transport_err ** 2) ** 0.5
                tm = m_liq
            else:
                # 2) Calcul classique pour consommables solides
                e_mass, t_mass, e_mass_err, missing_mats = self._calculate_mass_based_emissions_old(
                    code_nacres, consommable, quantity, conditionnement
                )
                # Facteur personnalisé (kg eCO₂/kg) pour produits vrac sans matériau défini
                if e_mass == 0.0 and custom_fe > 0.0:
                    masse_unitaire_g = self._safe_float(data_dict.get('masse_unitaire', 0.0))
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
                    error_message = (
                        f"WARN:Les matériaux suivants sont absents de la base et "
                        f"n'ont pas été comptabilisés :\n{noms}\n\n"
                        f"Vérifiez la base « empreinte_carbone_materiaux »."
                    )

        return (ep, ep_err, em, em_err, tm, error_message)

    def _calculate_mass_based_emissions_old(self, code_nacres, consommable, quantity, packaging=""):
        """
        Calcule l'empreinte carbone totale (production + fin de vie) d'un consommable
        solide à partir des masses unitaires et des matériaux de ses composants.

        Modèle de fin de vie :
          - Consommable (produit slots 1/2/3) → filière contaminée DASRI ou DIS,
            déterminée par le préfixe du code NACRES (cf. ui/end_of_life.py).
          - Emballage et conditionnement → incinération triée par matériau
            (cf. materials.eol_emission_factor_id).

        Si la base ne contient pas de facteur EoL pour un matériau (métaux par ex.),
        sa contribution EoL est ignorée silencieusement (pas considéré comme erreur).
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
        pack = clean_text(packaging)
        condt_col = getattr(self.dm, "CONDT_IJM_COL", "condt_ijm")
        if pack and condt_col in df_row.columns:
            exact_pack = df_row[df_row[condt_col].fillna("").astype(str).str.strip() == pack]
            if not exact_pack.empty:
                df_row = exact_pack
        if df_row.empty:
            return (0.0, 0.0, 0.0, [])
        row = df_row.iloc[0]

        # 3) Définir les composants à traiter, avec leur type (product / packaging)
        # et leur libellé d'emplacement (utile pour l'UI au déroulement).
        composants = [
            (self.dm.MASSE_G_COL,  self.dm.MATERIAU_COL, "product",   "Matériau principal"),
            (getattr(self.dm, "MASSE_G2_COL", None), getattr(self.dm, "MATERIAU2_COL", None), "product", "Matériau secondaire"),
            (getattr(self.dm, "MASSE_G3_COL", None), getattr(self.dm, "MATERIAU3_COL", None), "product", "Matériau tertiaire"),
            (self.dm.MASSE_EMBALLAGE_COL, self.dm.MATERIAU_EMBALLAGE_COL, "packaging", "Emballage secondaire"),
            (self.dm.MASSE_CONDITIONNEMENT_COL, self.dm.MATERIAU_CONDITIONNEMENT_COL, "packaging", "Conditionnement primaire"),
        ]

        # Facteur filière (DASRI/DIS) — uniforme pour tous les composants "product".
        # Résolu une seule fois, hors boucle.
        filiere_co2, filiere_unc, filiere = self.dm.get_filiere_factor(code_nacres)

        total_mass_kg = 0.0
        total_emission = 0.0
        total_unc_sq = 0.0
        missing_materials = []
        breakdown_components: list[dict] = []
        missing_eol_materials: list[str] = []

        # 4) Pour chaque composant, calculer production + fin de vie
        for col_masse, col_mat, comp_type, slot_label in composants:
            if col_masse is None or col_mat is None:
                continue
            # Lecture brute de la masse (g) — NaN doit être traité comme 0
            _raw = row.get(col_masse, 0.0)
            raw_masse = self._safe_float(_raw)
            # Si on est dans le conditionnement primaire, on divise par le nombre par conditionnement
            if col_masse == self.dm.MASSE_CONDITIONNEMENT_COL:
                nombre = self._safe_float(row.get(self.dm.NOMBRE_PAR_COND_COL, 1), default=1.0)
                if nombre <= 0:
                    continue
                raw_masse = raw_masse / nombre
            # Si on est dans l'emballage secondaire, on divise par le nombre partageant l'emballage
            elif col_masse == self.dm.MASSE_EMBALLAGE_COL:
                nb_emb = self._safe_float(
                    row.get(getattr(self.dm, "NOMBRE_PAR_EMBALLAGE_COL", "Nbr par emballage secondaire"), 1),
                    default=1.0,
                )
                if nb_emb <= 0:
                    nb_emb = 1.0
                raw_masse = raw_masse / nb_emb
            # On obtient la masse finale du composant
            masse_g = raw_masse
            materiau = row.get(col_mat, "") or ""

            # Ignorer si pas de masse ou matériau manquant
            if masse_g <= 0 or not materiau:
                continue

            # Récupérer le facteur CO₂ production (kgCO₂/kg) et son incertitude
            # AVANT d’accumuler la masse, pour ne pas compter une masse sans émission
            co2_per_kg, uncert_mat = self.dm.get_material_data(materiau)
            if co2_per_kg is None:
                missing_materials.append(materiau)
                continue

            # Conversion en kg et application de la quantité
            masse_kg = quantity * masse_g / 1000.0
            total_mass_kg += masse_kg

            # 4a) Production
            emission_prod = masse_kg * co2_per_kg
            total_emission += emission_prod
            total_unc_sq += (emission_prod * uncert_mat) ** 2

            # 4b) Fin de vie
            emission_eol = 0.0
            eol_co2_per_kg: float | None = None
            eol_unc: float | None = None
            eol_filiere: str | None = None
            eol_factor_name: str | None = None
            if comp_type == "product":
                # Filière contaminée : facteur uniforme par NACRES.
                if filiere_co2 is not None:
                    eol_co2_per_kg = filiere_co2
                    eol_unc = filiere_unc
                    eol_filiere = filiere
                    eol_factor_name = f"Filière {filiere}"
                    emission_eol = masse_kg * filiere_co2
                    total_emission += emission_eol
                    if filiere_unc is not None:
                        total_unc_sq += (emission_eol * filiere_unc) ** 2
            else:  # packaging / conditionnement
                co2_eol, unc_eol, eol_name = self.dm.get_material_eol_data(materiau)
                if co2_eol is not None:
                    eol_co2_per_kg = co2_eol
                    eol_unc = unc_eol
                    eol_factor_name = eol_name or ""
                    emission_eol = masse_kg * co2_eol
                    total_emission += emission_eol
                    if unc_eol is not None:
                        total_unc_sq += (emission_eol * unc_eol) ** 2
                else:
                    # Matériau sans EoL (métaux récupérés en mâchefers).
                    # On le signale dans le breakdown pour la traçabilité UI,
                    # mais ce n'est pas une erreur.
                    if materiau not in missing_eol_materials:
                        missing_eol_materials.append(materiau)

            # Tracer le composant dans le breakdown détaillé (utilisé par l'UI
            # pour le déroulement de ligne).
            breakdown_components.append({
                "type": comp_type,            # 'product' | 'packaging'
                "slot": slot_label,           # libellé humain (UI)
                "material": materiau,
                "mass_g_per_unit": float(masse_g),
                "mass_kg_total": float(masse_kg),
                "production": {
                    "co2_per_kg": float(co2_per_kg),
                    "co2": float(emission_prod),
                    "uncertainty_rel": float(uncert_mat),
                },
                "eol": {
                    "filiere": eol_filiere,            # DASRI / DIS / None
                    "factor_name": eol_factor_name,    # nom du facteur EoL appliqué
                    "co2_per_kg": eol_co2_per_kg,      # None si pas de facteur
                    "co2": float(emission_eol),
                    "uncertainty_rel": eol_unc,        # None si pas d'incertitude
                    "missing": eol_co2_per_kg is None, # True si pas de mapping (métal)
                },
            })

        total_unc = total_unc_sq ** 0.5

        # Construire et stocker le breakdown agrégé pour l'UI.
        prod_total = sum(c["production"]["co2"] for c in breakdown_components)
        eol_conso_total = sum(c["eol"]["co2"] for c in breakdown_components if c["type"] == "product")
        eol_packaging_total = sum(c["eol"]["co2"] for c in breakdown_components if c["type"] == "packaging")
        self.last_breakdown = {
            "components": breakdown_components,
            "totals": {
                "production": prod_total,
                "eol_consommable": eol_conso_total,
                "eol_packaging": eol_packaging_total,
                "total": total_emission,
                "mass_kg": total_mass_kg,
                "uncertainty": total_unc,
            },
            "filiere_consommable": filiere if filiere_co2 is not None else None,
            "missing_production": list(missing_materials),
            "missing_eol": missing_eol_materials,
        }

        return (total_emission, total_mass_kg, total_unc, missing_materials)



    def _calculate_liquid_emissions(self, code_nacres, volume_ml, consommable=None, packaging=""):
        """
        Calcule l'empreinte carbone d'un consommable liquide via volume (mL).
        """
        try:
            row = self.dm.get_liquid_data(code_nacres, consommable, packaging)
        except TypeError:
            row = self.dm.get_liquid_data(code_nacres, consommable)
        if row is None:
            return (0.0, 0.0, 0.0)
        return self._calculate_liquid_emissions_from_row(row, volume_ml)

    def _calculate_liquid_emissions_from_row(self, row, volume_ml):
        # Colonnes de la table liquid
        dens = self._safe_float(row.get("Densité (g/mL)", 0.0))
        conc = self._safe_float(row.get("Concentration (mg/mL)", 0.0))
        factor = self._safe_float(row.get("Facteur CO₂ (kg CO₂e/kg)", 0.0))
        uncert_pct = self._safe_float(row.get("Incertitude (%)", 0.0)) / 100.0

        unit = clean_text(row.get("Unité", "")).casefold()

        # quantité → masse (kg)
        # Pour les entrées IJM NA* solides/poudres rangées avec les liquides,
        # la quantité peut être saisie en g/kg au lieu d'un volume en mL.
        # Si densité disponible : masse = volume × densité / 1000
        # Sinon si concentration (mg/mL) : masse = volume × concentration (mg) / 1 000 000
        if unit in {"kg", "kilogramme", "kilogrammes"}:
            mass_kg = volume_ml
        elif unit in {"g", "gramme", "grammes"}:
            mass_kg = volume_ml / 1000.0
        elif dens > 0:
            mass_kg = dens * volume_ml / 1000.0
        elif conc > 0:
            mass_kg = volume_ml * conc / 1_000_000.0
        else:
            mass_kg = 0.0

        # émission + incertitude
        emission = mass_kg * factor
        error = emission * uncert_pct

        return (emission, mass_kg, error)
