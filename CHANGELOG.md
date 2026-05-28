# 📘 CHANGELOG – LABeCO₂

Toutes les modifications notables du projet seront consignées dans ce fichier avec ré-organisation des fichiers.

## [3.0] – 2026-05-28

### ✨ Migration vers SQLite et workflow contributeur

- **Bascule complète vers SQLite** comme format de stockage unifié :
  - une base de référence (`data/labeco2_reference.sqlite`) en lecture seule ;
  - une base de travail copiée au premier lancement dans le dossier utilisateur
    (`private/labeco2.sqlite` en dev, `~/Library/Application Support/LABeCO2/`
    sur macOS compilé, équivalents Windows/Linux) ;
  - variable d'environnement `LABECO2_SQLITE_PATH` pour surcharger le chemin ;
  - schéma versionné via `schema_migrations`, migrations dans `tools/migration/`.

- **Workflow contributeur statut-par-statut** :
  `pending` → `draft` → `validated` → `deprecated`, avec horodatage,
  identifiant du validateur, traçabilité par contribution.

- **Nouvel outil d'administration `tools/lab_admin.py`** avec 5 onglets :
  - Validation (filtres NACRES / fournisseur, attribution NACRES en masse,
    suggestions automatiques, contrôle qualité, ouverture de la fiche fournisseur) ;
  - Fusion / Conflits (import de contributions SQLite ou JSON, détection
    des doublons, résolution interactive) ;
  - Qualité (audit complet : sources manquantes, NACRES obsolètes,
    composants orphelins, doublons probables, valeurs hors plage) ;
  - Catalogue fournisseurs (édition des produits et de leurs URLs) ;
  - Import Scraping (aperçu coloré nouveau / mise à jour prix / déjà connu,
    sauvegarde automatique avant import).

- **Scraper fournisseur** (`tools/supplier_scraper/`) :
  crawler poli avec délai configurable, cache HTML, respect de `robots.txt` ;
  parser pour Fisher Scientific et VWR ; stockage en base privée
  (`private/supplier_scraping_lab.sqlite`) ; import contrôlé vers la base
  principale (les produits entrent en statut `pending` et nécessitent une
  validation manuelle).

### ✨ Améliorations du calculateur

- **Bouton 🌐 « fiche fournisseur »** à côté du combo Consommables : ouvre
  la page produit du fournisseur dans le navigateur. Pré-remplissage automatique
  de l'URL dans le champ Source du dialogue *Enrichir le consommable*.
- **Suggestions NACRES par mots-clés** dans la fenêtre de validation.
- **Combos NACRES et consommables** : popup limité à 15 entrées avec scrollbar,
  déroulement aligné exactement sous le widget (corrige le popup « volant »
  sur macOS).
- **Refonte des règles qualité** harmonisées entre `quality_check.py` et
  `tools/admin/workflow.py` (règles `missing_packaging`, `deprecated_nacres`,
  `liquid_missing_factor` alignées).
- **Bouton « Appliquer NACRES à la sélection »** dans l'onglet Validation
  pour traiter plusieurs lignes d'un coup.
- **Nettoyage de la cellule NACRES après édition** : la combobox d'édition
  se retire automatiquement, retour au texte simple en jaune (modification
  en attente).
- **Boutons « Ouvrir ↗ »** sur les champs Source et Lien dans le dialogue
  d'enrichissement (détection d'URL ou de DOI, ajout automatique du schéma
  `https://` ou `https://doi.org/`).

### 🛠 Changements techniques

- Bouton renommé : `Enrichir le consommable choisi` → `Enrichir le consommable`.
- `audit_25_mai_2026.txt` : journal d'audit des correctifs validation /
  qualité réalisés pendant la migration.
- 242 tests pytest passent (+ 11 sous-tests) ; tests dédiés aux règles qualité
  et au scraper.
- Ajout d'`audit qualité` automatisé après chaque réalignement de règles.

### 🚀 Note

Cette version marque une rupture franche avec les anciens fichiers HDF5/CSV.
Les bilans calculés avant V3.0 ne peuvent pas être rechargés directement
dans le calculateur ; ré-exporter en JSON depuis l'ancienne version reste
possible pour ré-import partiel.

---

## [2.1] – 2025-04-18
### ✨ Ajouts majeurs
- Implémentation d'une **nouvelle structure de l'application**, facilitant la maintenance et l'ajout de nouvelles fonctionnalités ;
- Ajout du support de **`ManipType`**, permettant de mieux catégoriser les types de calculs dans LABeCO₂ ;
- Intégration d'une **licence** :
  - GNU GPL v3 pour une utilisation libre et non commerciale ;
- Ajout des fichiers `LICENSE.txt` (GPL) ;
- Amélioration significative de **l’ergonomie** générale de l’application.

### 🛠 Changements techniques
- Refactorisation complète du code Python (séparation des fenêtres, meilleure organisation des modules) ;
- Meilleure gestion des dépendances ;
- Ajout d'un champ de recherche dynamique dans les interfaces de sélection.

### 🚀 Note
Cette version marque une base stable pour le développement futur.  
Elle introduit la structure de long terme du projet.

---