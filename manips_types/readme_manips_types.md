Auteur : Alexandre Souchaud
labeco2.contact@gmail.com
Licence : GNU GPL v3 ou ultérieure

# 🔧 Fichiers `a`, `b`, `c` — Construction des manipulations types dans LABeCO2

Ce dossier contient les scripts Python permettant de construire, gérer et éditer la base de données des **manipulations types** utilisées dans l'application **LABeCO2**. Ces manipulations types servent de modèles réutilisables pour calculer l'empreinte carbone d'activités expérimentales ou techniques standardisées.

---

## 📂 Structure des fichiers

### 1. `a_manips_type_db.py` : la base de données
Ce fichier définit la classe `ManipsTypeDB`, qui encapsule la logique de gestion de la base de données `manips_type.sqlite`.

Il contient :
- la création des tables `manips` et `manips_items`
- les méthodes pour :
  - ajouter une nouvelle manipulation (`add_manip`)
  - consulter et modifier les noms ou sources
  - récupérer les items associés à une manip

### 2. `b_create_manip_type_file.py` : insertion de manipulations types
Ce fichier permet de créer de nouvelles manipulations de type *native* (ou *user*) dans la base, via un appel à la méthode `add_manip()`.

💡 Il sert notamment à alimenter la base de données initiale avec des exemples standards.

### 3. `c_manage_manips_type.py` : interface terminal pour édition
Ce script propose un menu dans le terminal pour :
- lister toutes les manipulations types (avec ID, nom, et source)
- modifier leur nom
- modifier leur source (`native`, `user`, etc.)

Il permet de rapidement corriger ou mettre à jour les informations contenues dans la base via une interface simple.

---

## 📁 Base de données utilisée

La base SQLite utilisée est :  manips_types/manips_type.sqlite

Elle est automatiquement créée si elle n'existe pas. Elle contient :
- Une table `manips` avec les métadonnées des manipulations types (nom, source)
- Une table `manips_items` avec les objets (machines, consommables...) associés

---

## 💡 Exemple de structure de manipulation

Une manipulation type peut contenir plusieurs objets décrits comme suit :

```json
{
  "category": "Achats",
  "subcategory": "Pipettes",
  "subsubcategory": "LA11 - Vaccins",
  "name": "Pipettes stériles",
  "value": 10.0,
  "unit": "€",
  "quantity": 100.0
}
```

## NB : 
•	Les manipulations peuvent être marquées comme “native” (venant avec l’application) ou “user” (ajoutées par l’utilisateur).
•	Ce système permet d’initialiser un référentiel commun d’activités types à réutiliser dans d’autres parties de l’application LABeCO2.