📝 LABeCO2
Copiright © 2025 Alexandre Souchaud : tous droits reservés
## Contact
Pour toutes questions ou informations concernant le logiciel et ses droits, veuillez contacter : 
labeco2.contact@gmail.com

## Auteur
Alexandre Souchaud labeco2.contact@gmail.com
## Date de création de la version 1
1er Octobre 2024
## Date de création : 01/10/2024
## Date de la dernière version : 12/05/2026

## Version Actuelle V2.3.2
## DOI: 10.5281/zenodo.20135459
## Description

Ce calculateur de Bilan Carbone LabeCO2 est une application interactive développée en Python utilisant PyQt5 pour l’interface graphique. Elle permet de calculer et de visualiser les émissions de CO₂e (équivalent CO₂) liées aux activités de laboratoire. L’objectif est de sensibiliser les utilisateurs à leur empreinte carbone et de les aider à identifier les postes les plus énergivores pour adopter des pratiques plus durables.


## **Fonctionnalités**

- **Interface intuitive** : Sélectionnez des catégories, sous-catégories et sous-sous-catégories pour calculer vos émissions.
- **Gestion des machines personnalisées** : Calculez les émissions liées à l’utilisation de machines spécifiques (puissance, temps d’utilisation, type d’électricité).
- **Visualisation graphique** :
  - Graphiques en camembert interactifs.
  - Graphiques en barres empilées et proportionnelles.
  - Analyse par codes NACRES (4 premiers caractères affichés).
- **Gestion des données** :
  - Historique complet des calculs avec possibilité de modification.
  - Exportation et importation des données (JSON, CSV, Excel).
- **Compatibilité avec les codes NACRES** : Analyse des consommables avec une précision accrue.
- **Références transparentes** : Intégration des bases de données scientifiques pour garantir la fiabilité des résultats.

Ajout de capture d’écran

## Prérequis
<ul>
    <li>
        <span>Python :</span> 
        <span style="color: green;">Version 3.7 ou supérieure</span>
    </li>
    <li>Bibliothèques Python :
        <ul>
            <li><span style="color: green;">pandas</span></li>
            <li><span style="color: green;">PySide6</span></li>
            <li><span style="color: green;">matplotlib</span></li>
            <li><span style="color: green;">numpy</span></li>
            <li><span style="color: green;">adjustText</span></li>
        </ul>
    </li>
</ul>


Pour installer les dépendances : 

```bash
pip install -r requirements.txt
```
requirements.txt et autres se retrouvent dans le dossier "instalation". 


## Installation

<ul>
    <li>
        <span style="color: green;">1. Cloner le Répertoire</span>
        <pre>
        <code>
git clone https://github.com/votre-utilisateur/calculateur-bilan-carbone.git
cd calculateur-bilan-carbone
</code>
        </pre>
    </li>
    <li>
        <span style="color: green;">2. Créer un Environnement Virtuel (Optionnel mais Recommandé)</span>
        <pre>
        <code>
python -m venv venv
source venv/bin/activate  # Pour macOS/Linux
venv\Scripts\activate     # Pour Windows
        </code>
        </pre>
    </li>
    <li>
        <span style="color: green;">3. Installer les Dépendances</span>
        <pre>
        <code>
pip install -r requirements.txt
</code>
        </pre>
        <p>Note : Si le fichier <code>requirements.txt</code> n’est pas présent, installez manuellement les bibliothèques nécessaires :</p>
        <pre>
        <code>
pip install pandas PySide6 matplotlib numpy adjustText
</code>
        </pre>
    </li>
    <li>
        <span style="color: green;">4. Vérifier la base SQLite</span>
        <ul>
            <li>Assurez-vous que <code>data/labeco2_reference.sqlite</code> est présent.</li>
            <li>Au premier lancement, l'application initialise une base de travail SQLite depuis cette base de référence.</li>
        </ul>
    </li>
    <li>
        <span style="color: green;">5. Vérifier les Ressources</span>
        <ul>
            <li>Le dossier <code>images</code> doit contenir :</li>
            <ul>
                <li><code>Logo.png</code> : Le logo de l’application.</li>
                <li><code>icon.png</code> : L’icône de l’application.</li>
            </ul>
        </ul>
    </li>
</ul>

## Utilisation
<ul>
    <li>
        <span style="color: green;">1. Lancer l’Application</span>
        <pre>
        <code>python main.py</code>
        </pre>
    </li>
    <li>
        <span style="color: green;">2. Interagir avec l’Interface</span>
        <ul>
            <li><span style="color: green;">•</span> <b>Sélection de Catégories</b> : Choisissez une catégorie dans la liste déroulante pour commencer.</li>
            <li><span style="color: green;">•</span> <b>Sous-catégories et Recherches</b> : Affinez votre sélection en choisissant une sous-catégorie ou en utilisant la barre de recherche.</li>
            <li><span style="color: green;">•</span> <b>Saisie des Valeurs</b> : Entrez les valeurs demandées (par exemple, la quantité en kg, le nombre de jours, etc.).</li>
            <li><span style="color: green;">•</span> <b>Calculer le Bilan Carbone</b> : Cliquez sur le bouton <i>“Calculer le Bilan Carbone”</i> pour ajouter le calcul à l’historique.</li>
            <li><span style="color: green;">•</span> <b>Ajouter une Machine</b> : Si vous souhaitez calculer les émissions d’une machine spécifique, sélectionnez la catégorie <i>“Machine”</i> et renseignez les informations demandées.</li>
            <li><span style="color: green;">•</span> <b>Visualiser le Graphique</b> : Une fois vos calculs effectués, cliquez sur <i>“Valider”</i> pour générer le graphique en camembert.</li>
            <li><span style="color: green;">•</span> <b>Exporter/Importer des Données</b> : Utilisez les boutons correspondants pour sauvegarder ou charger vos calculs.</li>
        </ul>
    </li>
    <li>
        <span style="color: green;">3. Modifier ou Supprimer des Calculs</span>
        <ul>
            <li><span style="color: green;">•</span> <b>Modifier</b> : Double-cliquez sur un élément de l’historique pour modifier les valeurs.</li>
            <li><span style="color: green;">•</span> <b>Supprimer</b> : Sélectionnez un élément et cliquez sur <i>“Supprimer le calcul sélectionné”</i>.</li>
        </ul>
    </li>
</ul>

## **Structure du projet**

```python
LABeCO2/                          # Racine du projet
├── CHANGELOG.md                  # Historique complet des versions et correctifs
├── LICENCE.md                    # Licence MIT appliquée au projet
├── README.md                     # Documentation principale (présentation, install…)
├── requirements.txt              # Dépendances Python minimales (pip)
├── main.py                       # Point d’entrée CLI/GUI : lance l’app PySide6
│
├── data/
│   └── labeco2_reference.sqlite  # Base SQLite de référence (facteurs, NACRES, consommables)
│
├── private/
│   └── labeco2.sqlite            # Base SQLite de travail locale (créée/actualisée en dev)
│
├── assets/                       # Ressources graphiques
│   ├── Logo.png                  # Logo affiché dans l’interface/README
│   ├── icon.ico                  # Icône standard Windows
│   ├── icon.icns                 # Icône macOS (.app)
│
├── docs/                         # Documentation technique et installation
│
├── scenarios/                    # Gestion des « types de manip » et historiques
│   ├── manips_type.sqlite        # SQLite : types + paramètres par défaut
│   ├── example_history.csv       # Exemple d’historique utilisateur
│   └── *.json                    # Scénarios / historiques utilisateur exportés
│
├── styles/                       # Feuilles de style Qt (QSS)
│   └── styles.qss
│
├── utils/                        # Fonctions utilitaires transverses
│   ├── data_loader.py            # Ressources, chemins utilisateur et bootstrap SQLite
│   ├── color_utils.py            # Génération de palettes & conversions
│   ├── graph_utils.py            # Helpers matplotlib (couleurs cohérentes, labels)
│   └── readme_utils.md           # Notes dev sur les utils
│
└── ui/                           # Interface graphique (PySide6)
    ├── main_window.py            # Fenêtre principale : navigation + graphes
    ├── carbon_calculator.py      # Logique métier du calcul CO₂e
    ├── data_manager.py           # Chargement des DataFrames depuis SQLite
    ├── data_mass_window.py       # IHM dédiée aux facteurs et consommables
    ├── edit_calculation_dialog.py# Popup d’édition d’une ligne historique
    ├── UserManipDialog.py        # Gestion des scénarios « manips »
    └── graphiques/               # 6 types de graphiques interactifs
        ├── graph_1_pie_chart.py          # Camembert
        ├── graph_2_bar_chart.py          # Barres empilées (prix vs masse)
        ├── graph_3_proportional_bar_chart.py
        ├── graph_4_stacked_bar_consumables.py
        ├── graph_5_nacres_bar_chart.py   # Agrégation par code NACRES
        └── graph_6_proportional_bar_chart_mass.py
```
---

## **Graphiques disponibles**

### 1. **Diagrammes en secteurs**  
**Description :**  
Permet d’analyser la répartition des émissions de CO₂e par catégorie. Chaque segment du diagramme représente une proportion des émissions totales, facilitant l’identification des catégories les plus impactantes.  
**Utilisation typique :**  
Pour avoir une vue d’ensemble de la contribution des différentes catégories au bilan carbone global.

---

### 2. **Graphiques en barres empilées - Consommables (Quantité > 0)**  
**Description :**  
Affiche un graphique en barres empilées pour les consommables ayant une quantité supérieure à 0. Compare les émissions calculées en fonction du prix et de la masse des consommables.  
**Utilisation typique :**  
Pour évaluer l'empreinte carbone des consommables et identifier les consommables avec le plus d'impact.

---

### 3. **Graphiques en barres proportionnelles - Distribution par catégorie**  
**Description :**  
Montre une distribution proportionnelle des émissions de CO₂e par catégorie. Chaque barre est proportionnelle au total des émissions pour cette catégorie, avec une répartition interne par sous-catégorie.  
**Utilisation typique :**  
Pour comparer l'impact total des catégories tout en visualisant leurs proportions internes.

---

### 4. **Graphiques en barres empilées - Masse vs Monétaire**  
**Description :**  
Compare les émissions de CO₂e des consommables calculées selon leur coût monétaire et leur masse. Affiche des barres empilées pour chaque consommable, permettant une comparaison directe entre les deux approches de calcul.  
**Utilisation typique :**  
Pour comprendre les différences entre les calculs basés sur le coût monétaire et la masse des consommables.

---

### 5. **Graphiques en barres proportionnelles - Masse selon les codes NACRES**  
**Description :**  
Affiche un graphique en barres proportionnelles basé sur la masse des consommables, regroupés par leurs codes NACRES (les 4 premiers caractères). Les proportions internes reflètent la répartition des sous-catégories.  
**Utilisation typique :**  
Pour analyser l’impact des consommables regroupés par code NACRES, selon leur empreinte carbone basée sur la masse.

---

### 6. **Graphiques en barres empilées - Monétaire selon les codes NACRES**  
**Description :**  
Affiche un graphique en barres empilées pour les consommables regroupés par leurs codes NACRES, montrant leur empreinte carbone calculée selon leur coût monétaire.  
**Utilisation typique :**  
Pour visualiser l’impact des consommables par code NACRES, en se basant sur leurs coûts.

---
---
## Détails du Code

### 1. Fichier Principal
**main_window.py**  
Contient la logique principale de l’application, y compris les classes et méthodes suivantes :

- **MainWindow** : Gère l’interface utilisateur principale, les interactions utilisateur, et le calcul des émissions de carbone. Elle intègre des fonctionnalités comme l'historique des calculs, la gestion des consommables, et les graphiques interactifs.

### 2. Fonctionnalités Clés
- **Chargement des Données** :  
  Utilise la classe `DataManager` pour lire et gérer les données issues des fichiers, y compris les facteurs d’émission, les consommables, et les machines.
- **Interface avec PySide6** :  
  Crée une interface graphique intuitive avec des widgets, des layouts, et des signaux connectés aux actions de l’utilisateur.
- **Graphiques avec Matplotlib** :  
  Intègre plusieurs types de graphiques interactifs (diagramme en secteurs, barres empilées, barres proportionnelles, etc.) directement dans l’interface utilisateur.
- **Gestion des Machines** :  
  Permet de calculer les émissions liées à l’utilisation de machines spécifiques en fonction de leur puissance, temps d’utilisation, et type d’électricité.
- **Exportation/Importation des Données** :  
  Sauvegarde l’historique des calculs dans différents formats (JSON, CSV, Excel) et permet de charger des données existantes pour reprise ou comparaison.
- **Gestion des Consommables** :  
  Fournit une interface dédiée à la gestion et à la sélection des consommables, incluant un filtrage basé sur les codes NACRES.

---

### 3. Exemple Visuel des Classes Principales

| Classe         | Description                                                                 |
|----------------|-----------------------------------------------------------------------------|
| **MainWindow** | Gère l'interface utilisateur principale, les sélecteurs de catégories, les calculs et l'affichage des résultats. |
| **PieChartWindow** | Affiche un diagramme en secteurs pour la répartition des émissions. |
| **BarChartWindow** | Affiche des graphiques en barres empilées pour les comparaisons de données. |
| **ProportionalBarChartWindow** | Montre une distribution proportionnelle des émissions par catégorie. |
| **StackedBarConsumablesWindow** | Compare les consommables en fonction des calculs basés sur leur prix ou leur masse. |
| **NacresBarChartWindow** | Analyse les consommables selon leur code NACRES et leurs émissions carbone. |

---

### 4. Fonctionnalités Clés

| Fonctionnalité                  | Détail                                                                 |
|---------------------------------|-----------------------------------------------------------------------|
| **Chargement des Données**      | Gestion des données via `DataManager`, incluant les facteurs d'émission et les consommables. |
| **Interface PySide6**           | Création de widgets, gestion de signaux et événements pour une interface fluide et intuitive. |
| **Graphiques Matplotlib**       | Génération de graphiques interactifs intégrés directement dans l'application. |
| **Gestion des Machines**        | Calcul précis des émissions pour des machines personnalisées, basé sur leur puissance et leur temps d’utilisation. |
| **Exportation/Importation** | Sauvegarde ou reprise de l’historique dans des formats flexibles comme JSON, CSV ou Excel. |
| **Consommables et Codes NACRES**| Analyse des consommables avec des graphiques spécifiques pour leurs coûts carbone basés sur leur prix ou leur masse. |

## Contribuer

Les contributions sont les bienvenues ! Si vous souhaitez améliorer cette application :
	1.	Forkez le Projet
	2.	Créez une Branche pour Votre Fonctionnalité
```bash
git checkout -b ma-nouvelle-fonctionnalite
```
	3.	Commitez Vos Modifications
```bash
git commit -m "Ajout d'une nouvelle fonctionnalité"
```

	4.	Pushez vers la Branche
```bash
git push origin ma-nouvelle-fonctionnalite
```

	5.	Ouvrez une Pull Request

## Licence

Ce projet est sous licence MIT. Veuillez consulter le fichier [LICENSE](./LICENSE) pour plus de détails.

---

## Remerciements

### Données et Contributions

- **Labo 1point5** : Les données utilisées proviennent de la base de données fournie par le collectif Labo 1point5, visant à réduire l'empreinte carbone dans les laboratoires de recherche.
- **Bibliothèques Open Source** :
  - [PySide6](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/index.html)
  - [Matplotlib](https://matplotlib.org/)
  - [Pandas](https://pandas.pydata.org/)
  - [NumPy](https://numpy.org/)
  - [AdjustText](https://github.com/Phlya/adjustText)

---

## Sources et Références

### Sources

- **[Base Carbone®](https://base-empreinte.ademe.fr/)**  
  Source officielle pour les données de l'ADEME (Agence de la Transition Écologique).

- **[Labo 1point5](https://labos1point5.org/)**  
  Plateforme collaborative pour la réduction de l'empreinte carbone dans les laboratoires de recherche.
  Les données ont été téléchargée en Octobre 2024 et était les dernières alors mise en ligne par le collectif.

- **[PlasticsEurope](https://plasticseurope.org/fr/)**  
  Organisation représentant les fabricants de plastiques en Europe, fournissant des données sur l'industrie.

- **[OCDE](https://www.oecd.org/fr/data/)**  
  Organisation de Coopération et de Développement Économiques, base de données sur les indicateurs environnementaux.

- **[440 Megatonnes](https://440megatonnes.ca/fr/insight/mesurer-lempreinte-carbone-du-plastique/)**  
  Analyse des impacts carbone du plastique.

- **[Ansell - Reducing the impact of disposable glove manufacturing on the environment](https://www.ansell.com/-/media/projects/ansell/website/pdf/industrial/safety-briefing-blogs/emea/reducing-the-impact-of-disposable-glove-manufacturing-on-the-environment/safety-briefing_reducing-the-impact-of-disposable-glove-manufacturing-on-the-environment_en.ashx?rev=96e1cea169c54f0b995d5a4c1f2876d0)**  
  Article d'Ansell discutant des mesures pour réduire l'impact environnemental de la fabrication des gants jetables.

---

### Articles Scientifiques

- **"Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consumables"**  
  Isabella Ragazzi, publié dans [PLOS](https://doi.org/10.1371/journal.pstr.0000080), septembre 2023.  
  DOI : [10.1371/journal.pstr.0000080](https://doi.org/10.1371/journal.pstr.0000080).

- **"The environmental impact of personal protective equipment in the UK healthcare system"**  
  Reed, S. et al., publié dans [Journal of the Royal Society of Medicine](https://journals.sagepub.com/doi/epub/10.1177/01410768211001583), 2021.  
  DOI : [10.1177/01410768211001583](https://journals.sagepub.com/doi/epub/10.1177/01410768211001583).

---

## Contact

Pour toute question ou suggestion, veuillez contacter Alexandre Souchaud à l’adresse souchaud@bio.ens.psl.eu

Ensemble, réduisons notre empreinte carbone et agissons pour un avenir durable ! 🌍
