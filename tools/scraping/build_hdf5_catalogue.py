"""
build_hdf5_catalogue.py

Convertit catalogue_complet.csv en HDF5 pour l'application LABeCO2.

Usage :
    python tools/scraping/build_hdf5_catalogue.py

Sortie :
    data/mass_factors/data_eCO2_masse_consommable.hdf5  (remplace l'existant)
"""

import os
import re
import pandas as pd

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR   = os.path.dirname(os.path.dirname(BASE_DIR))
CSV_PATH   = os.path.join(BASE_DIR, "output", "catalogue_complet.csv")
HDF5_PATH  = os.path.join(ROOT_DIR, "data", "mass_factors", "data_eCO2_masse_consommable.hdf5")
BACKUP_PATH = HDF5_PATH + ".backup"

# Colonnes numériques à convertir (virgule → point)
NUMERIC_COLS = [
    "Masse unitaire (g)",
    "Masse unitaire deuxieme materiaux (g)",
    "Masse unitaire troisième materiaux (g)",
    "Masse emballage unitaire (g)",
    "Masse condionnement (g)",
    "Nbr par conditionnement",
    "prix_ht_ijm",
    "nb_unites_ijm",
    "prix_unitaire_ijm",
]


def to_float(series):
    return pd.to_numeric(
        series.astype(str).str.replace(',', '.', regex=False).str.strip(),
        errors='coerce'
    )


def build():
    print(f"Lecture de : {CSV_PATH}")
    df = pd.read_csv(CSV_PATH, dtype=str).fillna("")

    # ── 1. Normaliser Code NACRES → 4 chars (code_nacres_court) ─────────────
    df["Code NACRES"] = df["code_nacres_court"].str.strip().str.upper()
    df.drop(columns=["code_nacres_court"], inplace=True)

    # ── 2. Nettoyer score_match : supprimer les "REMOVED(...)" ───────────────
    df["score_match"] = df["score_match"].apply(
        lambda v: "" if str(v).startswith("REMOVED") else v
    )

    # ── 3. Convertir colonnes numériques ─────────────────────────────────────
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = to_float(df[col])

    # ── 4. Supprimer la colonne ID (sera régénérée si besoin) ────────────────
    if "ID" in df.columns:
        df.drop(columns=["ID"], inplace=True)

    # ── 5. Backup de l'ancien fichier ────────────────────────────────────────
    if os.path.exists(HDF5_PATH):
        import shutil
        shutil.copy2(HDF5_PATH, BACKUP_PATH)
        print(f"Backup sauvegardé : {BACKUP_PATH}")

    # ── 6. Sauvegarde HDF5 ───────────────────────────────────────────────────
    df.to_hdf(HDF5_PATH, key="data", mode="w", complevel=5)

    print(f"\n{len(df)} produits enregistrés dans : {HDF5_PATH}")
    avec_masse  = df["Masse unitaire (g)"].notna().sum()
    avec_prix   = df["prix_unitaire_ijm"].notna().sum()
    print(f"  Avec données masse  : {avec_masse}")
    print(f"  Avec prix IJM       : {avec_prix}")
    print(f"  Colonnes            : {list(df.columns)}")


if __name__ == "__main__":
    build()
