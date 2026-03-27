# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# utils/data_loader.py

import sys
import os
import shutil
import pandas as pd
from PySide6.QtGui import QPixmap

def get_user_data_path():
    """
    Retourne le répertoire de données utilisateur, persistant entre sessions.
    En mode compilé (PyInstaller), sys._MEIPASS est temporaire — on utilise
    un dossier dans le profil utilisateur à la place.
    En mode développement, retourne la racine du projet.
    """
    if getattr(sys, 'frozen', False):
        if sys.platform == 'darwin':
            base = os.path.join(os.path.expanduser('~'), 'Library',
                                'Application Support', 'LABeCO2')
        elif sys.platform == 'win32':
            base = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')),
                                'LABeCO2')
        else:
            base = os.path.join(os.path.expanduser('~'), '.labeco2')
        os.makedirs(base, exist_ok=True)
        return base
    else:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def init_user_data():
    """
    Lors du premier lancement en mode compilé, copie les fichiers HDF5 modifiables
    depuis sys._MEIPASS vers le dossier utilisateur persistant.
    Les fichiers en lecture seule (base GES, matériaux) restent dans _MEIPASS.
    """
    if not getattr(sys, 'frozen', False):
        return  # Rien à faire en développement

    user_path = get_user_data_path()
    bundle_path = sys._MEIPASS

    # Fichiers écrits par l'utilisateur → doivent être dans user_path
    writable_files = [
        os.path.join("data_masse_eCO2", "data_eCO2_masse_consommable.hdf5"),
        os.path.join("data_masse_eCO2", "data_eCO2_liquides_consommable.hdf5"),
        os.path.join("manips_types", "manips_type.sqlite"),
    ]

    for rel_path in writable_files:
        dest = os.path.join(user_path, rel_path)
        if not os.path.exists(dest):
            src = os.path.join(bundle_path, rel_path)
            if os.path.exists(src):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest)
                print(f"[init] Copié : {rel_path} → {dest}")


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

