# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# manips_types/a_manips_type_db.py

import sqlite3
import os
import sys

# Fonction utilitaire pour compatibilité PyInstaller
def resource_path(relative_path):
    """
    Récupère le chemin absolu vers une ressource, compatible avec PyInstaller.
    """
    try:
        # PyInstaller crée un dossier temporaire _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class ManipsTypeDB:
    def __init__(self, db_path='manips_types/manips_type.sqlite'):
        """
        Initialise la connexion SQLite et crée les tables si elles n'existent pas.
        :param db_path: Chemin du fichier de base de données SQLite.
        """
        self.db_path = resource_path(db_path)
        # Connexion à la base (créée si inexistante)
        self.conn = sqlite3.connect(self.db_path)
        # Pour récupérer les lignes sous forme de dictionnaires (clé = nom de colonne)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self):
        """
        Crée les tables 'manips' et 'manips_items' si elles n'existent pas déjà.
        La table 'manips' a un champ 'source' pour distinguer les manips "native" vs "user".
        """
        create_manips_table = """
        CREATE TABLE IF NOT EXISTS manips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'native'
        );
        """
        create_manips_items_table = """
        CREATE TABLE IF NOT EXISTS manips_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manip_id INTEGER NOT NULL,
            category TEXT,
            subcategory TEXT,
            subsubcategory TEXT,
            code_nacres TEXT,
            name TEXT,
            value REAL,
            unit TEXT,
            days REAL,
            year REAL,
            electricity_type TEXT,
            quantity REAL,
            consommable TEXT,
            FOREIGN KEY (manip_id) REFERENCES manips(id)
        );
        """

        cursor = self.conn.cursor()
        cursor.execute(create_manips_table)
        cursor.execute(create_manips_items_table)
        self.conn.commit()

    def add_manip(self, manip_name, items_list, source="native"):
        """
        Ajoute une nouvelle manip et ses items dans la base.
        :param manip_name: str, nom de la manip
        :param items_list: liste de dictionnaires décrivant les items, ex:
            [
              {
                "category": "Machine",
                "subcategory": "Microscope",
                "subsubcategory": "KC21 - Litiere",
                "name": "Microscope 3000",
                "value": 5.0,
                "unit": "kWh"
              },
              {
                "category": "Achats",
                "subcategory": "Pipettes",
                "subsubcategory": "LA11 - Vaccins",
                "name": "Pipettes stériles",
                "value": 10.0,
                "unit": "€",
                "quantity": 100.0,
                "consommable": ""
              }
            ]
        :param source: "native" ou "user" par ex. pour distinguer l'origine
        """
        cursor = self.conn.cursor()
        # 1) Insérer la manip dans la table manips
        cursor.execute("INSERT INTO manips (name, source) VALUES (?, ?)", (manip_name, source))
        manip_id = cursor.lastrowid  # Récupère l'ID auto-généré pour la manip

        # 2) Insérer chaque item dans la table manips_items
        for item in items_list:
            cursor.execute("""
                INSERT INTO manips_items 
                    (manip_id, category, subcategory, subsubcategory, name, value, unit, days, year, electricity_type, quantity, consommable)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                manip_id,
                item.get("category", ""),
                item.get("subcategory", ""),
                item.get("subsubcategory", ""),
                item.get("name", ""),
                item.get("value", 0.0),
                item.get("unit", ""),
                item.get("days", 0.0),
                item.get("year", 0.0),
                item.get("electricity_type", ""),
                item.get("quantity", 0.0),
                item.get("consommable", "")
            ))
        print("ADD MANIP : ", items_list)
        self.conn.commit()
    
    def update_manip_name(self, manip_id, new_name):
        """
        Met à jour le nom d'une manip existante.
        :param manip_id: int, l'ID de la manip à modifier
        :param new_name: str, le nouveau nom
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE manips
            SET name = ?
            WHERE id = ?
        """, (new_name, manip_id))
        self.conn.commit()

    def update_manip_source(self, manip_id, new_source):
        """
        Met à jour la source d'une manip existante ('user', 'native', etc.).
        :param manip_id: int, l'ID de la manip à modifier
        :param new_source: str, la nouvelle source
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE manips
            SET source = ?
            WHERE id = ?
        """, (new_source, manip_id))
        self.conn.commit()

    def list_manips_with_id(self):
        """
        Retourne la liste (id, name, source) de toutes les manips, classées par id.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, source FROM manips ORDER BY id ASC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def list_manips(self, source=None):
        """
        Retourne la liste des noms de manip disponibles dans la table `manips`.
        :param source: None, "native", ou "user".
                       Si None, on retourne toutes les manips; sinon on filtre sur la colonne 'source'.
        """
        cursor = self.conn.cursor()
        if source is None:
            cursor.execute("SELECT name FROM manips ORDER BY name ASC")
        else:
            cursor.execute("SELECT name FROM manips WHERE source = ? ORDER BY name ASC", (source,))
        rows = cursor.fetchall()
        return [row["name"] for row in rows]

    def get_manip_items(self, manip_name):
        """
        Récupère tous les items d'une manip, identifiée par son nom.
        Retourne une liste de dict.
        """
        cursor = self.conn.cursor()
        # Récupérer l'ID de la manip via son nom
        cursor.execute("SELECT id FROM manips WHERE name = ?", (manip_name,))
        row = cursor.fetchone()
        if not row:
            return []  # Si la manip n'existe pas, on renvoie une liste vide

        manip_id = row["id"]
        # Maintenant on récupère tous les items associés à ce manip_id
        cursor.execute("""
            SELECT category, subcategory, subsubcategory, name, value, unit, days, year, electricity_type, quantity, consommable
            FROM manips_items
            WHERE manip_id = ?
        """, (manip_id,))
        rows = cursor.fetchall()

        items = []
        for r in rows:
            items.append({
                "category": r["category"],
                "subcategory": r["subcategory"],
                "subsubcategory": r["subsubcategory"],
                "name": r["name"],
                "value": r["value"],
                "unit": r["unit"],
                "days": r["days"],
                "year": r["year"],
                "electricity_type": r["electricity_type"],
                "quantity": r["quantity"],
                "consommable": r["consommable"]
            })
        return items