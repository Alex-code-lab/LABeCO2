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


def load_data():
    data_file = resource_path('data_base_GES1point5/data_base_GES1point5.hdf5')
    try:
        df = pd.read_hdf(data_file, key='purchases_factors')
    except (KeyError, ValueError):
        # Fallback : lire la première clé disponible
        with pd.HDFStore(data_file, mode='r') as store:
            keys = store.keys()
        if not keys:
            raise ValueError(f"Le fichier HDF5 '{data_file}' ne contient aucune table.")
        df = pd.read_hdf(data_file, key=keys[0])
    return df

