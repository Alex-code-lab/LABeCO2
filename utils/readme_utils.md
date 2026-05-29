# 📁 LABeCO2 — dossier `utils/`

Ce dossier contient les modules utilitaires pour la construction, la gestion et la visualisation des données dans l'application **LABeCO2**.

---

## Fichiers et fonctionnalités

### 1. `color_utils.py`

Fonctions utilitaires liées à la gestion des couleurs dans les graphiques :
- **Palette de couleurs cohérente** pour chaque grande catégorie (ex : Véhicules, Achats…)
- `CATEGORY_COLORS` : Dictionnaire de couleurs associées à chaque catégorie d'émission
- `CATEGORY_ORDER` : Ordre canonique d'affichage des catégories
- `generate_color_shades(base_color, num_shades)` : Génère des nuances claires/sombres à partir d’une couleur de base (pour décliner des sous-catégories ou graduer une intensité sur les graphiques).

### 2. `data_loader.py`

Outils de chargement de ressources et données :
- `resource_path(relative_path)` : Renvoie le chemin absolu des fichiers (compatible avec PyInstaller et exécution locale)
- `load_logo()` : Charge le logo de l’application (utilisé dans l’interface graphique PySide6)
- `resolve_sqlite_path(base_path, user_path)` : Résout ou initialise la base SQLite de travail depuis `data/labeco2_reference.sqlite`

Ce module centralise la gestion des fichiers de données ou de ressources (images…), garantissant leur accessibilité aussi bien en développement qu’en version distribuée.

### 3. `graph_utils.py`

Fonctions pour faciliter la génération de graphiques avec Matplotlib :
- `plot_pie_chart(ax, labels, values, colors, title)` : Création rapide d’un diagramme en secteurs (camembert) personnalisable, avec gestion des couleurs, titres et pourcentages.

Ce fichier permet de garder le code de visualisation propre et réutilisable partout dans l’application.

---

## 🔗 Utilisation

Ces modules sont faits pour être **importés** et utilisés dans les autres parties de LABeCO2, afin de :
- standardiser l'affichage graphique,
- centraliser les accès aux données,
- garantir une expérience utilisateur cohérente.

---

## Auteur

Alexandre Souchaud  
Projet LABeCO2 
Licence : [GNU GPL v3 ou ultérieure](https://www.gnu.org/licenses/gpl-3.0.fr.html)
---
