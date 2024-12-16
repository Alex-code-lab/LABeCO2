import pandas as pd

# Données des matériaux
data = {
    "Matériau": [
        "Polypropylène (PP)", "Polyéthylène (PE)", "Polystyrène (PS)",
        "Polyéthylène téréphtalate (PET)", "Polychlorure de vinyle (PVC)",
        "Polytétrafluoroéthylène (PTFE)", "Polycarbonate (PC)",
        "Polyméthacrylate de méthyle (PMMA)", "Acier inoxydable",
        "Aluminium", "Papier", "Carton", "Verre"
    ],
    "Équivalent CO₂ (kg eCO₂/kg)": [
        3.0, 2.5, 3.5, 4.0, 2.7, 6.5, 5.0, 6.0, 6.5, 11.0, 1.05, 0.95, 0.8
    ],
    "Précision (%)": [
        "±10%", "±10%", "±10%", "±15%", "±10%", "±20%", "±15%", "±15%", "±15%", "±20%", "±5%", "±5%", "±10%"
    ],
    "Source": [
        "Base Empreinte® - ADEME", "Base Empreinte® - ADEME", "Base Empreinte® - ADEME",
        "Base Empreinte® - ADEME", "Base Empreinte® - ADEME", "Base Empreinte® - ADEME",
        "Base Empreinte® - ADEME", "Base Empreinte® - ADEME", "France Stratégie",
        "France Stratégie", "Base Empreinte® - ADEME", "Base Empreinte® - ADEME",
        "Base Empreinte® - ADEME"
    ]
}

# Création du DataFrame
df = pd.DataFrame(data)

# Afficher le DataFrame
print(df)

# Enregistrer dans un fichier HDF5
df.to_hdf("./data_mass_eq/empreinte_carbone.h5", key='data', mode='w')