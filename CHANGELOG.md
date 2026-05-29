# 📘 CHANGELOG – LABeCO₂

Toutes les modifications notables du projet seront consignées dans ce fichier avec ré-organisation des fichiers.

## [3.1] – 2026-05-29

### ✨ Calcul de la fin de vie (incinération)

L'empreinte carbone des consommables solides inclut désormais l'**incinération
en fin de vie**, en plus de la production. Le total affiché dans l'historique
est `production + fin de vie`, et un panneau « Détail du calcul » sous le
tableau d'historique décompose contribution par contribution.

- **Modèle d'attribution** (par composant) :
  - **Consommable** (matériaux principal/secondaire/tertiaire) → filière
    contaminée **DASRI** ou **DIS**, routée automatiquement par préfixe NACRES
    (`NA/NL/NM` → DIS chimie, `NB/NC/ND/NE` → DASRI bio, défaut DASRI
    conservatif). Pas de choix utilisateur.
  - **Emballage** et **conditionnement** → facteur d'incinération par
    matériau (filière banale triée).

- **Facteurs ajoutés** (8, tous d'origine ADEME Base Empreinte) :
  - `DAS/Incinération` = 0,943 kgCO₂e/kg (qualité 1/5, ±50 %, BC v23.10) ;
  - `DIS/Incinération` = 0,844 kgCO₂e/kg (qualité 3/5, ±20 %, BC v23.10) ;
  - Plastique générique = 2,27 ; PE/PP/PB/PS = 3,04 ; PVC rigide = 2,25 ;
    Verre = 0,054 (toutes BI v3.0, qualité 5/5, peer-reviewed thinkstep/GaBi) ;
  - Carton = 0,120 ; PET pétrosourcé = 2,14 (BC v23.10).
  - Cross-check par Rizan et al. 2021 (DASRI hôpital UK = 1,074 kgCO₂e/kg) →
    cohérent à 12 % près avec la fiche ADEME DAS.

- **Mapping matériaux** : 12/14 matériaux de référence reliés à leur facteur
  EoL (`materials.eol_emission_factor_id`). Métaux (Acier inoxydable,
  Aluminium) laissés sans EoL — les mâchefers sont récupérés à froid, pas
  d'émission directe.

### 🎨 UI — Panneau « Détail du calcul »

- Affichage sous l'historique des calculs : sélectionner une ligne pour voir :
  - Résumé : masse totale, filière retenue, totaux Production / EoL
    consommable / EoL emballage / **Total** ;
  - Tableau composant par composant : matériau, masse, kg CO₂e production,
    kg CO₂e fin de vie, filière ou facteur EoL appliqué ;
  - Avertissement qualité contextuel : bandeau orange explicite quand la
    filière DASRI est utilisée (qualité 1/5, ±50 %, cross-check Rizan 2021).
- L'incertitude affichée combine en quadrature les incertitudes production
  et fin de vie.

### 🛠 Changements techniques

- **Migration DB v3 (`add_end_of_life_factors`)** dans
  `tools/migration/migrate_v3_end_of_life_factors.py` : idempotente,
  backup automatique, applicable à n'importe quelle base via `--db-path`
  (ex. base utilisateur `private/labeco2.sqlite`).
- **Colonne `materials.eol_emission_factor_id`** ajoutée par la migration ;
  ALTER défensif dans `ensure_app_schema` pour les bases antérieures à v3.
- **Module `ui/end_of_life.py`** : routage NACRES → filière + mapping
  filière → nom de facteur en base.
- **API `DataManager`** étendue : `get_material_eol_data`,
  `get_eol_factor_by_name`, `get_filiere_factor`.
- **API `CarbonCalculator`** :
  - `_calculate_mass_based_emissions_old` ajoute désormais la contribution
    EoL au total `em` et combine les incertitudes en quadrature.
  - Attribut public `last_breakdown` (dict) repeuplé à chaque appel de
    `compute_emission_data` — exposé pour la consommation UI.
- **Test de non-régression** `test_solide_discret_pp_tube_15ml` mis à jour
  pour refléter le changement intentionnel (em : 0,218755 → 0,281936 ;
  em_err : 0,020794 → 0,037820).
- **Tests** : 222 → 225 verts (6 nouveaux tests EoL + 3 sur le breakdown).
- **Référence justificative complète** : tableau xlsx des 60 fiches ADEME
  analysées avec valeurs, indicateurs DQR et recommandations LABeCO₂ —
  archivé hors-repo dans `private/incineration/facteurs_emission_incineration_ademe.xlsx`.

### 🚀 Note

Cette mise à jour est **rétro-compatible**. Les bases utilisateur antérieures
à v3.1 chargent toujours sans erreur (ALTER défensif), mais l'EoL n'est
calculé que lorsque la migration v3 a été appliquée — sinon la contribution
EoL est nulle silencieusement. Pour appliquer la migration sur sa base de
travail :

```sh
python tools/migration/migrate_v3_end_of_life_factors.py --db-path private/labeco2.sqlite
```

---

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