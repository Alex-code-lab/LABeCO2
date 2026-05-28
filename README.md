# 📝 LABeCO₂

Calculateur de bilan carbone pour laboratoires de recherche.

- **Auteur** : Alexandre Souchaud — labeco2.contact@gmail.com
- **Version actuelle** : V3.0 du 28/05/2026
- **DOI** : [10.5281/zenodo.15240634](https://doi.org/10.5281/zenodo.15240634)
- **Licence** : GNU GPL v3 (ou ultérieure)
- **Date de création** : 1er octobre 2024

> Copyright © 2024-2026 Alexandre Souchaud. Tous droits réservés.
> Pour toute question concernant le logiciel et ses droits : labeco2.contact@gmail.com

---

## Description

LABeCO₂ est une application graphique (PySide6) permettant aux laboratoires de recherche
de calculer et visualiser leurs émissions de CO₂e. L'objectif est de sensibiliser à
l'empreinte carbone et d'identifier les postes les plus émetteurs pour adopter des
pratiques plus durables.

Depuis la V3.0, l'ensemble des facteurs d'émission, consommables et historiques est
stocké dans une **base SQLite unifiée**, avec un workflow contributeur (proposition,
validation, dépréciation) et un outil d'administration dédié (`lab_admin`).

---

## Fonctionnalités principales

### Calculateur (`main.py`)
- Sélection par catégorie / sous-catégorie / code NACRES.
- Calcul d'émissions par **masse**, **prix** ou **code NACRES** selon les données disponibles.
- Gestion des machines personnalisées (puissance × temps × mix électrique).
- Historique complet des calculs avec modification, suppression, export (JSON / CSV / Excel).
- Bouton **🌐 fiche fournisseur** pour ouvrir directement la page du produit chez son fournisseur.
- Saisie de **manips types** pour automatiser des scénarios récurrents.
- ~10 visualisations interactives (camembert, barres empilées, agrégation NACRES,
  transport, couverture par catégorie, Pareto…).

### Administration des données (`tools/lab_admin.py`)

> ⚠️ **Outil destiné aux contributeurs et administrateurs, pas aux utilisateurs
> finaux du calculateur.**

`lab_admin` sert à préparer, vérifier et fusionner les données qui alimentent
la base de référence partagée entre tous les utilisateurs. Il ne calcule pas
d'empreinte carbone.

Cinq onglets :
- **Validation** : passage en revue des entrées en attente, attribution des codes NACRES
  (suggestion automatique, application en masse), validation ou rejet.
- **Fusion / Conflits** : import d'un fichier de contribution (SQLite ou JSON),
  détection des doublons, résolution des conflits avant fusion.
- **Qualité** : audit complet de la base (entrées sans source, codes NACRES obsolètes,
  composants orphelins, etc.).
- **Catalogue fournisseurs** : édition des produits et de leur lien fournisseur.
- **Import Scraping** : import d'observations issues du scraper en statut `pending`,
  pour validation manuelle.

### Scraper fournisseur (`tools/supplier_scraper/`)
Crawler poli (délai configurable, cache HTML, respect de robots.txt) qui collecte
des références produit chez des fournisseurs publics (Fisher Scientific, VWR, etc.).
Les observations sont stockées dans une base privée puis importées vers la base
principale via `lab_admin`.

---

## Workflow contributif

Trois rôles distincts :

| Rôle | Outil | Que peut-il faire ? |
|---|---|---|
| **Utilisateur** | `main.py` | Calculer son bilan, ajouter ses propres consommables / facteurs en local via *Enrichir le consommable*, *Ajouter un facteur d'émission*, *Ajouter un consommable*. |
| **Contributeur** | `main.py` puis envoi du fichier | Enrichir sa base locale puis envoyer son `labeco2.sqlite` à un administrateur pour partage avec la communauté. |
| **Administrateur** | `tools/lab_admin.py` | Recevoir plusieurs contributions, fusionner, contrôler la qualité, valider, publier une base de référence enrichie dans la prochaine release. |

### Comment contribuer concrètement

1. **Vous (utilisateur ou contributeur)** ajoutez vos consommables et facteurs
   manquants dans le calculateur. Ils sont marqués en statut `pending`/`draft`
   dans **votre** base locale.
2. **Vous envoyez votre fichier `labeco2.sqlite`** à un administrateur du projet
   (cf. *Contact* en bas du README). Vos ajouts n'écrasent rien chez les autres :
   ils restent locaux tant qu'ils ne sont pas validés.
3. **Les administrateurs** utilisent `lab_admin` pour fusionner les bases
   reçues, vérifier la cohérence (sources, codes NACRES, valeurs hors plage),
   et valider les entrées qui méritent d'entrer dans la base officielle.
4. **La base enrichie est redistribuée** dans la prochaine release de LABeCO₂.

C'est ce processus qui permet à la base de référence de grandir et de s'affiner
avec l'usage, tout en gardant un contrôle qualité centralisé.

---

## Prérequis

- **Python 3.11** ou supérieur
- Dépendances Python listées dans `requirements.txt` (PySide6, pandas, matplotlib, numpy, …)

---

## Installation

```bash
git clone https://github.com/Alex-code-lab/LABeCO2.git
cd LABeCO2

# Environnement virtuel recommandé
python -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

Au premier lancement, l'application initialise une copie de travail SQLite à partir
de `data/labeco2_reference.sqlite` :
- **Mode dev** : dans `private/labeco2.sqlite`.
- **Mode compilé** : dans `~/Library/Application Support/LABeCO2/data/` (macOS),
  `%APPDATA%/LABeCO2/data/` (Windows), `~/.labeco2/data/` (Linux).

La variable d'environnement `LABECO2_SQLITE_PATH` permet de surcharger ce chemin.

---

## Utilisation

### Calculateur
```bash
python main.py
```
1. Choisissez une catégorie (Achats, Machine, Transport…).
2. Affinez par sous-catégorie, code NACRES, consommable.
3. Renseignez la quantité, le prix ou la masse selon le mode disponible.
4. Cliquez **Calculer le Bilan Carbone** : la ligne est ajoutée à l'historique.
5. Visualisez les résultats via les boutons de graphiques.
6. Exportez ou importez votre bilan (JSON / CSV / Excel).

### Outil d'administration
```bash
python tools/lab_admin.py            # ouvre la base par défaut
python tools/lab_admin.py --db PATH  # cible une autre base
```

### Scraper (optionnel, pour contributeurs)
```bash
python -m tools.supplier_scraper.main --config tools/supplier_scraper/config.yaml
# Mode dry-run actif par défaut ; les observations sont collectées
# dans private/supplier_scraping_lab.sqlite.
```

---

## Structure du projet

```
LABeCO2/
├── main.py                       # Point d'entrée du calculateur (PySide6)
├── CHANGELOG.md
├── README.md
├── LICENCE                       # GNU GPL v3
├── requirements.txt
│
├── data/
│   ├── labeco2_reference.sqlite  # Base SQLite de référence (read-only)
│   ├── nacres_codes/             # Référentiel NACRES
│   ├── ges1point5/               # Facteurs Labos 1point5
│   ├── mass_factors/             # Facteurs d'émission massique
│   └── catalogues/               # Catalogues fournisseurs
│
├── ui/                           # Interface PySide6 et logique calcul
│   ├── main_window.py            # Fenêtre principale du calculateur
│   ├── carbon_calculator.py      # Logique métier du calcul CO₂e
│   ├── data_manager.py           # Chargement des données depuis SQLite
│   ├── data_mass_window.py       # Saisie / enrichissement de consommable
│   ├── edit_calculation_dialog.py
│   ├── user_manip_dialog.py      # Gestion des manips types
│   ├── validate_window.py        # Widget de validation (réutilisé par lab_admin)
│   ├── validation_ops.py         # Opérations SQLite de validation
│   ├── validation_details.py
│   ├── quality_check.py          # Audit qualité d'une base SQLite
│   ├── sqlite_schema.py          # Schéma SQLite officiel
│   ├── sqlite_legacy_adapter.py  # Compatibilité avec l'ancien format DataFrame
│   ├── sqlite_writer.py
│   ├── nacres_metadata.py
│   ├── display_utils.py
│   └── charts/                   # ~10 visualisations matplotlib
│       ├── pie_chart.py
│       ├── bar_chart_consumables.py
│       ├── bar_chart_price_mass.py
│       ├── bar_chart_proportional.py
│       ├── nacres_bar_chart.py
│       ├── nacres_proportional.py
│       ├── coverage_overview.py
│       ├── coverage_by_category.py
│       ├── pareto_chart.py
│       ├── transport_chart.py
│       └── …
│
├── tools/                        # Outils d'admin et contribution
│   ├── lab_admin.py              # Application d'administration (validation, fusion, qualité)
│   ├── admin/                    # Modules métier (workflow, suggestions NACRES, fusion…)
│   ├── contribution_io.py        # Lecture/écriture des fichiers de contribution
│   ├── import_contribution.py
│   ├── export_contribution.py
│   ├── export_excel.py
│   ├── validate_entries.py
│   ├── migration/                # Scripts de migration de schéma
│   └── supplier_scraper/         # Scraper fournisseur (crawler poli + import)
│
├── utils/                        # Helpers transverses (chemins, couleurs, graphes…)
├── styles/                       # Feuilles de style Qt (QSS)
├── assets/                       # Logo, icônes, captures
├── scenarios/                    # Manips types et historiques utilisateur
│   └── manips_type.sqlite
├── docs/                         # Documentation technique
├── tests/                        # Tests pytest
└── private/                      # Données utilisateur locales (non versionnées)
    ├── labeco2.sqlite
    └── supplier_scraping_lab.sqlite
```

---

## Contribuer

Les contributions sont les bienvenues — corrections de bugs, nouvelles données,
nouveaux fournisseurs, améliorations UX :

```bash
git checkout -b ma-fonctionnalite
# travail, tests, commits
git push origin ma-fonctionnalite
```

Ouvrez ensuite une Pull Request sur [github.com/Alex-code-lab/LABeCO2](https://github.com/Alex-code-lab/LABeCO2).

Pour proposer de nouveaux facteurs d'émission ou consommables, utilisez l'outil
`lab_admin` : il exporte un fichier de contribution qu'un validateur pourra
fusionner dans la base de référence.

---

## Licence

Distribué sous **GNU GPL v3 ou ultérieure** (utilisation libre, non commerciale).
Voir le fichier [LICENCE](./LICENCE) pour le texte complet.
Détails : <https://www.gnu.org/licenses/gpl-3.0.fr.html>.

---

## Citer LABeCO₂

> Souchaud, A. *LABeCO₂ — Calculateur de bilan carbone pour laboratoires de recherche*.
> Version V3.0, 2026. DOI : [10.5281/zenodo.15240634](https://doi.org/10.5281/zenodo.15240634).

---

## Remerciements et sources

### Données

- **[Labos 1point5](https://labos1point5.org/)** — Collectif pour la réduction de
  l'empreinte carbone dans les laboratoires de recherche. Données téléchargées
  initialement en octobre 2024 ; mises à jour avec la nomenclature NACRES 2026.
- **[Base Carbone® / ADEME](https://base-empreinte.ademe.fr/)** — Facteurs d'émission
  officiels de l'Agence de la Transition Écologique.
- **[PlasticsEurope](https://plasticseurope.org/fr/)** — Données industrielles plastiques.
- **[OCDE](https://www.oecd.org/fr/data/)** — Indicateurs environnementaux.
- **[440 Megatonnes](https://440megatonnes.ca/fr/insight/mesurer-lempreinte-carbone-du-plastique/)** —
  Analyse de l'empreinte carbone du plastique.
- **[Ansell – Reducing the impact of disposable glove manufacturing](https://www.ansell.com/)** —
  Impact environnemental des gants jetables.

### Articles scientifiques de référence

- Ragazzi, I. (2023). *Using life cycle assessments to guide reduction in the carbon
  footprint of single-use lab consumables.* PLOS Sustainability and Transformation.
  DOI : [10.1371/journal.pstr.0000080](https://doi.org/10.1371/journal.pstr.0000080).
- Reed, S. et al. (2021). *The environmental impact of personal protective equipment
  in the UK healthcare system.* Journal of the Royal Society of Medicine.
  DOI : [10.1177/01410768211001583](https://doi.org/10.1177/01410768211001583).

### Bibliothèques

[PySide6](https://doc.qt.io/qtforpython-6/), [Matplotlib](https://matplotlib.org/),
[Pandas](https://pandas.pydata.org/), [NumPy](https://numpy.org/).

---

## Contact

Alexandre Souchaud — **labeco2.contact@gmail.com**

> *Ensemble, réduisons notre empreinte carbone et agissons pour un avenir durable.* 🌍
