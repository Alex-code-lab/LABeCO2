# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# manips_types/c_manage_manips.py
import sys
import os
from a_manips_type_db import ManipsTypeDB

def main():
    # On suppose que le fichier .sqlite est dans un dossier particulier :
    db_path = os.path.join("manips_types", "manips_type.sqlite")
    db = ManipsTypeDB(db_path=db_path)

    while True:
        print("\n=== Gestion des Manips ===")
        print("1) Lister toutes les manips")
        print("2) Modifier le nom d'une manip")
        print("3) Modifier la source d'une manip")
        print("4) Quitter")

        choice = input("Votre choix : ").strip()
        if choice == '1':
            list_all_manips(db)
        elif choice == '2':
            update_manip_name(db)
        elif choice == '3':
            update_manip_source(db)
        elif choice == '4':
            print("Au revoir !")
            sys.exit(0)
        else:
            print("Choix invalide.")

def list_all_manips(db):
    manips = db.list_manips_with_id()
    print("\nListe des manips (ID - Nom - Source) :")
    for m in manips:
        print(f"ID={m['id']} | name={m['name']} | source={m['source']}")

def update_manip_name(db):
    print("\n** Modifier le nom d'une manip **")
    manip_id = input("Entrez l'ID de la manip à modifier : ").strip()
    new_name = input("Nouveau nom : ").strip()
    if not manip_id.isdigit():
        print("ID invalide.")
        return
    db.update_manip_name(int(manip_id), new_name)
    print(f"Le nom de la manip ID={manip_id} a été mis à jour en : {new_name}")

def update_manip_source(db):
    print("\n** Modifier la source d'une manip **")
    manip_id = input("Entrez l'ID de la manip à modifier : ").strip()
    new_source = input("Nouvelle source (ex: 'native' ou 'user') : ").strip()
    if not manip_id.isdigit():
        print("ID invalide.")
        return
    db.update_manip_source(int(manip_id), new_source)
    print(f"La source de la manip ID={manip_id} est maintenant : {new_source}")

if __name__ == "__main__":
    main()