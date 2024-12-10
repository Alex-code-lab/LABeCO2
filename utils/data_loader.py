import os
import pandas as pd

def load_data(data_file_path):
    """
    Charge les données depuis un fichier HDF5.

    Paramètres :
    ------------
    data_file_path : str
        Chemin du fichier HDF5.

    Retour :
    --------
    pandas.DataFrame :
        Données chargées sous forme de DataFrame.
    """
    if not os.path.exists(data_file_path):
        raise FileNotFoundError(f"Fichier de données introuvable : {data_file_path}")

    try:
        return pd.read_hdf(data_file_path)
    except Exception as e:
        raise RuntimeError(f"Erreur lors du chargement des données : {e}")