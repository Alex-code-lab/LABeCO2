# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# utils/data_loader.py

import sys
import os
import pandas as pd
from PySide6.QtGui import QPixmap

def resource_path(relative_path):
    """Obtenir le chemin absolu vers les ressources, fonctionne pour le développement et PyInstaller"""
    try:
        # PyInstaller crée un dossier temporaire et stocke le chemin dans _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    return os.path.join(base_path, relative_path)

def load_logo():
    image_path = resource_path('images/Logo.png')
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Impossible de charger l'image: {image_path}")
    
    pixmap = QPixmap(image_path)
    return pixmap

# def load_data():
#     # data_file = resource_path('data_base_GES1point5/data_base_GES1point5.hdf5')
#     # data_file = resource_path('data_base_GES1point5/GES1point5_purchases_factors_PER1p5_v1-0-2023.h5')
#     data_file = resource_path('data_base_GES1point5/data_base_GES1point5.hdf5')
#     # Le fichier HDF5 contient plusieurs tables (datasets) ; il faut préciser la clé.
#     # La table compatible avec l'ancien format "Achats" est "purchases_factors".
#     try:
#         df = pd.read_hdf(data_file, key="purchases_factors")
#     except (ValueError, KeyError):
#         # Si la clé n'existe pas, on affiche les clés disponibles pour faciliter le debug.
#         with pd.HDFStore(data_file, mode="r") as store:
#             keys = store.keys()
#         raise ValueError(
#             f"Impossible de charger les données : key must be provided when HDF5 file contains multiple datasets. "
#             f"Clé attendue: 'purchases_factors'. Clés disponibles : {keys}"
#         )

#     return df
# def load_data

def load_data():
    data_file = resource_path('data_base_GES1point5/data_base_GES1point5.hdf5')
    df = pd.read_hdf(data_file)
    return df

# def load_data(data_file_path):
#     """
#     Charge les données depuis un fichier HDF5.

#     Paramètres :
#     ------------
#     data_file_path : str
#         Chemin du fichier HDF5.

#     Retour :
#     --------
#     pandas.DataFrame :
#         Données chargées sous forme de DataFrame.
#     """
#     if not os.path.exists(data_file_path):
#         raise FileNotFoundError(f"Fichier de données introuvable : {data_file_path}")

#     try:
#         return pd.read_hdf(data_file_path)
#     except Exception as e:
#         raise RuntimeError(f"Erreur lors du chargement des données : {e}")