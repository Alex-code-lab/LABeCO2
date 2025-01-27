📝 LabeCO2

## Description

Ce calculateur de Bilan Carbone LabeCO2 est une application interactive développée en Python utilisant PyQt5 pour l’interface graphique. Elle permet de calculer et de visualiser les émissions de CO₂e (équivalent CO₂) liées aux activités de laboratoire. L’objectif est de sensibiliser les utilisateurs à leur empreinte carbone et de les aider à identifier les postes les plus énergivores pour adopter des pratiques plus durables.

## Fonctionnalités 

- **Interface Intuitive** : Choisissez des catégories pour calculer les émissions.
- **Ajout de Machines** : Calculez les émissions pour des machines spécifiques en saisissant leur puissance et temps d’utilisation.
- **Historique des Calculs** : Gérez vos calculs précédents et ajustez-les pour affiner les résultats.
- **Exportation et Importation** : Exportez vos données en CSV ou importez des données pour reprise.
- **Graphiques** : Visualisez les émissions avec des graphiques intégrés.

Capture d’écran

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
pip install pandas PyQt5 matplotlib numpy adjustText
</code>
        </pre>
    </li>
    <li>
        <span style="color: green;">4. Télécharger les Données</span>
        <ul>
            <li>Assurez-vous que le fichier de données <code>data_base.hdf5</code> est présent dans le dossier <code>data_base_GES1point5</code>.</li>
            <li>Ce fichier contient les facteurs d’émission nécessaires au calcul du bilan carbone.</li>
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
LABeCO₂/
├── main.py                           # Point d'entrée principal
├── windows/                          # Interface utilisateur et gestionnaires graphiques
│   ├── main_window.py                # Fenêtre principale
│   ├── graphiques/                   # Gestion des graphiques
│   │   ├── bar_chart.py              # Graphiques en barres
│   │   ├── nacres_bar_chart.py       # Barres pour les codes NACRES
│   │   ├── proportional_bar_chart.py # Barres proportionnelles
│   │   ├── stacked_bar_consumables.py# Barres empilées pour consommables
│   └── data_mass_window.py           # Gestion des données massiques
├── utils/                            # Fonctions utilitaires
│   ├── color_utils.py                # Génération de couleurs et nuances
│   ├── data_loader.py                # Chargement des données
├── data_base_GES1point5/             # Données des facteurs d’émission
│   └── data_base.hdf5
├── images/                           # Fichiers image requis
│   ├── Logo.png                      # Logo de l'application
│   └── icon.png                      # Icône de l'application
├── requirements.txt                  # Liste des dépendances Python
└── README.md                         # Documentation du projet
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

### Détails du Code

#### 1. Fichier Principal
**main.py**  
Contient la logique principale de l’application, y compris les classes suivantes :
- **MainWindow** : Gère l’interface utilisateur, les interactions, et les calculs d’émissions.
- **ChartWindow** : Gère la création du graphique en camembert pour visualiser les émissions.

#### 2. Fonctionnalités Clés
- **Chargement des Données** :  
  Utilise la bibliothèque `pandas` pour lire le fichier HDF5 contenant les facteurs d’émission.
- **Interface avec PyQt5** :  
  Crée des widgets, des layouts, et connecte les signaux et slots pour interagir avec l’utilisateur de manière fluide.
- **Graphiques avec Matplotlib** :  
  Génère des visualisations intégrées dans l’interface PyQt5, permettant un affichage interactif et clair des données.
- **Gestion des Machines** :  
  Permet d’ajouter des machines personnalisées et de calculer leurs émissions en fonction de leur puissance et de leur temps d’utilisation.
- **Exportation/Importation des Données** :  
  Sauvegarde les calculs dans un fichier CSV ou charge des données depuis un fichier existant.

#### Exemple Visuel

##### Classes Principales
| Classe         | Description                                                                 |
|----------------|-----------------------------------------------------------------------------|
| **MainWindow** | Gère l’interface principale, les interactions utilisateur, et les calculs. |
| **ChartWindow**| Crée et affiche des graphiques pour visualiser la répartition des émissions.|

##### Fonctionnalités Clés
| Fonctionnalité                  | Détail                                                                 |
|---------------------------------|-----------------------------------------------------------------------|
| **Chargement des Données**      | Lecture du fichier HDF5 avec les données des facteurs d’émission.     |
| **Interface PyQt5**             | Widgets, signaux, et layouts pour une utilisation intuitive.          |
| **Graphiques Matplotlib**       | Création de graphiques interactifs intégrés à l’application.          |
| **Gestion des Machines**        | Ajout de machines personnalisées pour un calcul précis des émissions.|
| **Exportation/Importation CSV** | Sauvegarde ou récupération des calculs pour une utilisation flexible. |


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

Ce projet est sous licence MIT. Veuillez consulter le fichier LICENSE pour plus de détails.

Remerciements

	•	Labo 1point5 : Les données utilisées sont issues de la base de données fournie par le collectif Labo 1point5.
	•	Bibliothèques Open Source :
	•	PyQt5
	•	Matplotlib
	•	Pandas
	•	NumPy
	•	AdjustText

## Contact

Pour toute question ou suggestion, veuillez contacter Alexandre Souchaud à l’adresse souchaud@bio.ens.psl.eu

Ensemble, réduisons notre empreinte carbone et agissons pour un avenir durable ! 🌍