import pandas as pd

# Données des matériaux
data_materiau = {
    "Materiau": [
        "Polypropylène (PP)", "Polyéthylène (PE)", "Polystyrène (PS)",
        "Polyéthylène téréphtalate (PET)", "Polychlorure de vinyle (PVC)", "Polytétrafluoroéthylène (PTFE)",
        "Polycarbonate (PC)", "Polyméthacrylate de méthyle (PMMA)", "Acier inoxydable",
        "Aluminium", "Papier", "Carton", 
        "Verre", "Nitrile",
    ],
    "Equivalent CO₂ (kg eCO₂/kg)": [
        3.0, 2.5, 3.5,
        4.0, 2.7, 6.5,
        5.0, 6.0, 6.5,
        11.0, 1.05, 0.95,
        0.8, 6.4
    ],
    "Precision (%)": [
        "±10%", "±10%", "±10%",
        "±15%", "±10%", "±20%",
        "±15%", "±15%", "±15%",
        "±20%", "±5%", "±5%",
        "±10%", "±20%"
    ],
    "Source": [
        "Base Empreinte® - ADEME", "Base Empreinte® - ADEME", "Base Empreinte® - ADEME",
        "Base Empreinte® - ADEME", "Base Empreinte® - ADEME", "Base Empreinte® - ADEME",
        "Base Empreinte® - ADEME", "Base Empreinte® - ADEME", "France Stratégie",
        "France Stratégie", "Base Empreinte® - ADEME", "Base Empreinte® - ADEME",
        "Base Empreinte® - ADEME", "Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consum DOI: 10.1371/journal.pstr.0000080"

    ]
}

# Données des matériaux
data_solvant = {
    "Solvant": [
        "Acetone", "Ethanol", "Ethyl acetate", 
        "Formic acid", "Isopropanol", "Methanol",
        "Toluene", "Dichloromethane (DME)", "Cytoclopentyl methyl ether (CPME)", 
        "N-Methyl-2-pyrrolidone (NMP)", "Heptane"
    ],
    "Equivalent CO₂ (kg eCO₂/kg)": [
        2.3 , 2.1, 1.5,
        2.5, 1.7, 1.1,
        1.6, 5.0, 1.8,
        4.8, 1.1
    ],
    "Precision (%)": [
        "±15%", "±15%", "±15%",
        "±15%", "±15%", "±15%",
        "±15%", "±15%", "±15%",
        "±15%", "±15%",
    ],
    "Source": [
        "Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consum DOI: 10.1371/journal.pstr.0000080",
        "Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consum DOI: 10.1371/journal.pstr.0000080",
        "Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consum DOI: 10.1371/journal.pstr.0000080",
        "Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consum DOI: 10.1371/journal.pstr.0000080",
        "Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consum DOI: 10.1371/journal.pstr.0000080",
        "Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consum DOI: 10.1371/journal.pstr.0000080",
        "Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consum DOI: 10.1371/journal.pstr.0000080",
        "Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consum DOI: 10.1371/journal.pstr.0000080",
        "Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consum DOI: 10.1371/journal.pstr.0000080",
        "Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consum DOI: 10.1371/journal.pstr.0000080",
        "Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consum DOI: 10.1371/journal.pstr.0000080"
    ]
}

# Création du DataFrame
d_mat = pd.DataFrame(data_materiau)
d_solv = pd.DataFrame(data_solvant)
# Afficher le DataFrame
print(d_mat)
print(d_solv)

# Enregistrer dans un fichier HDF5
d_mat.to_hdf("./data_masse_eCO2/empreinte_carbone_materiaux.h5", key='data', mode='w')
d_solv.to_hdf("./data_masse_eCO2/empreinte_carbone_solvants.h5", key='data', mode='w')