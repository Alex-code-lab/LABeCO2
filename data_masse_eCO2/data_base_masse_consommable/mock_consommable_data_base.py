import pandas as pd
import random

# Liste des codes NACRES autorisés
allowed_codes = ["02", "03", "04", 
                 "11", "12", "13", "14", "15", "16", "17",
                 "21", "22", "23", "24"]

# Générer 100 entrées
data_100 = {
    "Consommable": [f"Consommable {i}" for i in range(1, 101)],
    "Marque": [f"Marque {chr(65 + i % 26)}" for i in range(100)],
    "Référence": [f"REF{i:03}" for i in range(1, 101)],
    "Code NACRES": [f"NB{random.choice(allowed_codes)}" for _ in range(100)],
    "Masse unitaire (g)": [round(random.uniform(5, 60), 2) for _ in range(100)],
    "Matériau": random.choices(["Polypropylène (PP)", "Verre", "Polystyrène (PS)"], k=100),
    "Source/Signature": ["ChatGPT"] * 100,
}

# Création du DataFrame
df_100 = pd.DataFrame(data_100)

# Sauvegarde au format CSV
df_100.to_csv('./data_masse_eCO2/mock_consumables_100.csv', index=False)

# Sauvegarde au format HDF5
df_100.to_hdf('./data_masse_eCO2/mock_consumables_100.hdf5', key='data', mode='w', index=False)

df_100