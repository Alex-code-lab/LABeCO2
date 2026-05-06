# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# data_base_GES1Point5/make_table_data_1point5.py

# toutes les datas de la base de données sont issues des données de labos1.5
import pandas as pd
import glob
import os

# 1) Définir le chemin vers le dossier contenant tous les .tsv
input_folder = './'

# 2) Récupérer la liste de tous les fichiers .tsv
all_files = glob.glob(os.path.join(input_folder, '*.tsv'))

# 3) Créer une liste pour stocker temporairement les DataFrame
df_list = []

# 4) Parcourir chaque fichier .tsv
for file in all_files:
    # Lire chaque fichier TSV dans un DataFrame Pandas
    df = pd.read_csv(file, sep='\t')  # ajuster le sep si besoin

    # Forcer la catégorie "Achats" pour les fichiers de type purchases
    if "purchases" in os.path.basename(file).lower():
        df["category"] = "Achats"

    df_list.append(df)

# 5) Fusionner tous les DataFrame en un seul
final_df = pd.concat(df_list, ignore_index=True)

# final_df['subcategory'] = final_df['subcategory'].replace(
#         'consommables',
#         'Consommables (Matières premières, produits chimiques/biologiques et organismes vivants)'
#     )

# 6) Exporter le DataFrame final au format HDF5
#    Le paramètre 'key' est obligatoire, vous pouvez lui donner le nom que vous voulez
output_file = './table_unique.csv'
final_df.to_csv(output_file)#, key='data', mode='w')

print(f"Fichier HDF5 généré : {output_file}")

# 7) Exporter le DataFrame final au format HDF5
output_hdf5 = '../data_base_GES1point5.hdf5'

# Conversion explicite des colonnes string pandas en object (compat PyTables)
final_df_h5 = final_df.copy()
for col in final_df_h5.columns:
    if pd.api.types.is_string_dtype(final_df_h5[col].dtype):
        final_df_h5[col] = final_df_h5[col].astype(object)

        final_df_h5.to_hdf(
    output_hdf5,
    key='data',
    mode='w',
    format='table'
)
        
print(f"Fichier CSV généré : {output_file}")
print(f"Fichier HDF5 généré : {output_hdf5}")