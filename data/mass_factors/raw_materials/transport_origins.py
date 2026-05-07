# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# data/mass_factors/raw_materials/transport_origins.py
#
# Génère data_transport_origins.hdf5
# Sources : ADEME Base Carbone® (routier, ferroviaire, aérien, maritime)
#           Carbone 4 — https://www.carbone4.com/analyse-faq-fret
#           HelloCarbo — https://www.hellocarbo.com/blog/calculer/bilan-carbone-transport/
#
# Formule appliquée : kgCO₂e/kg = (distance_km × facteur_gCO₂e_t_km) / 1 000 000
# Valeurs finales reprises telles quelles depuis le document de synthèse LABeCO₂.

import pandas as pd
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parents[1]

data = {
    "Origine": [
        "Inconnue (défaut)",
        "France",
        "Europe",
        "USA",
        "Asie",
        "Afrique",
        "Europe (express avion)",
        "USA (express avion)",
        "Asie (express avion)",
        "Afrique (express avion)",
    ],
    "Distance (km)": [14000, 500, 1500, 8000, 20000, 10000, 1500, 8000, 20000, 10000],
    "Mode": [
        "Maritime + camion",
        "Camion",
        "Camion + ferroviaire",
        "Maritime + camion",
        "Maritime + camion",
        "Maritime + routier",
        "Avion cargo",
        "Avion cargo",
        "Avion cargo",
        "Avion cargo",
    ],
    "Facteur officiel (kg CO₂e/t.km)": [
        0.00554, 0.086, 0.0798, 0.00554, 0.00554, 0.00554,
        1.9, 1.9, 1.9, 1.9,
    ],
    "Facteur transport (kg CO₂e/kg)": [
        0.265, 0.043, 0.12, 0.18, 0.35, 0.20,
        2.85, 15.2, 38.0, 19.0,
    ],
    "Incertitude": [
        0.30, 0.15, 0.20, 0.20, 0.20, 0.20,
        0.15, 0.15, 0.15, 0.15,
    ],
    "Source": [
        "Estimation LABeCO₂ — moyenne USA/Asie maritime (14 000 km)",
        "ADEME Base Carbone® - transport routier marchandises",
        "ADEME Base Carbone® - transport routier + ferroviaire",
        "ADEME Base Carbone® - transport maritime",
        "ADEME Base Carbone® - transport maritime",
        "ADEME Base Carbone® - transport maritime",
        "ADEME Base Carbone® - transport aérien",
        "ADEME Base Carbone® - transport aérien",
        "ADEME Base Carbone® - transport aérien",
        "ADEME Base Carbone® - transport aérien",
    ],
}

df = pd.DataFrame(data)
print(df.to_string())

out_path = OUTPUT_DIR / "data_transport_origins.hdf5"
df.to_hdf(out_path, key="data", mode="w")
print(f"\nFichier généré : {out_path}")
