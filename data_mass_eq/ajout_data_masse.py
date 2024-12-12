import pandas as pd

# Initialiser un DataFrame avec un exemple initial
columns = ["Nom de l'objet", "Référence", "Masse unitaire (g)", "Matériau", "Source/Signature"]
df = pd.DataFrame(columns=columns)

# Ajouter les tubes Falcon de 15 ml avec une signature
df = pd.concat([df, pd.DataFrame([{
    "Nom de l'objet": "Tube Falcon 15ml",
    "Référence": "N/A",
    "Masse unitaire (g)": 6.7,
    "Matériau": "Polypropylène (PP)",
    "Source/Signature": "Alexandre Souchaud"
}])], ignore_index=True)

def ajouter_objet(df):
    """Fonction pour ajouter un nouvel objet au DataFrame."""
    print("\nAjout d'un nouvel objet.")
    
    # Entrée utilisateur pour chaque champ
    nom = input("Entrez le nom de l'objet : ").strip()
    while not nom:
        print("Le nom de l'objet ne peut pas être vide.")
        nom = input("Entrez le nom de l'objet : ").strip()
    
    reference = input("Entrez la référence de l'objet : ").strip()
    while not reference:
        print("La référence de l'objet ne peut pas être vide.")
        reference = input("Entrez la référence de l'objet : ").strip()
    
    while True:
        masse_str = input("Entrez la masse unitaire (en grammes) de l'objet : ").strip()
        masse_str = masse_str.replace(',', '.')  # Remplacer la virgule par un point
        try:
            masse = float(masse_str)
            break
        except ValueError:
            print("Erreur : La masse doit être un nombre valide. Réessayez.")
    
    materiau = input("Entrez le matériau de l'objet : ").strip()
    while not materiau:
        print("Le matériau de l'objet ne peut pas être vide.")
        materiau = input("Entrez le matériau de l'objet : ").strip()
    
    source = input("Entrez la source ou signature (par exemple, votre nom ou une base de données) : ").strip()
    while not source:
        print("La source/signature ne peut pas être vide.")
        source = input("Entrez la source ou signature : ").strip()
    
    # Ajouter au DataFrame
    nouvel_objet = {
        "Nom de l'objet": nom,
        "Référence": reference,
        "Masse unitaire (g)": masse,
        "Matériau": materiau,
        "Source/Signature": source
    }
    df = pd.concat([df, pd.DataFrame([nouvel_objet])], ignore_index=True)
    
    print(f"\nL'objet '{nom}' a été ajouté avec succès.")
    return df

def sauvegarder_donnees(df, fichier="materiaux_labo.h5"):
    """Sauvegarde les données dans un fichier HDF5."""
    if df.empty:
        print("Aucune donnée à sauvegarder.")
    else:
        df.to_hdf(fichier, key="materiaux", mode="w")
        print(f"\nLes données ont été sauvegardées dans le fichier {fichier}.")

def afficher_donnees(df):
    """Afficher le contenu du DataFrame."""
    if df.empty:
        print("\nAucune donnée disponible.")
    else:
        print("\nDonnées actuelles :")
        print(df)

# Menu interactif
while True:
    print("\n--- Menu ---")
    print("1. Ajouter un nouvel objet")
    print("2. Afficher les données")
    print("3. Sauvegarder et quitter")
    choix = input("Entrez votre choix (1/2/3) : ").strip()
    
    if choix == "1":
        df = ajouter_objet(df)
    elif choix == "2":
        afficher_donnees(df)
    elif choix == "3":
        sauvegarder_donnees(df)
        print("\nProgramme terminé. À bientôt!")
        break
    else:
        print("Choix invalide, veuillez réessayer.")