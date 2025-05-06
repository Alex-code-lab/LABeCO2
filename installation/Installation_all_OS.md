# Installation générale de LABeCO2

Ce guide unifié fournit une procédure d’installation pour tous les utilisateurs, quel que soit leur système d’exploitation (Windows, macOS ou Linux).

---

## 1. Prérequis généraux

- **Python 3.11** installé sur votre machine
- **Un terminal fonctionnel** (PowerShell, Terminal macOS ou Bash)
- Facultatif mais recommandé : [Visual Studio Code](https://code.visualstudio.com/) avec l’extension Python

---

## 2. Installation de Python 3.11

### Sous **Windows**
- Télécharger Python 3.11 ici : https://www.python.org/downloads/windows/
- Pendant l’installation, **cocher "Add Python to PATH"**
- Vérifier ensuite dans le terminal :
  ```powershell
  py -3.11 -V
  ```

### Sous **macOS**
- Installer [Homebrew](https://brew.sh/) si ce n’est pas déjà fait
- Puis :
  ```bash
  brew install python@3.11
  ```

### Sous **Linux (Ubuntu/Debian)**
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-distutils
```

---

## 3. Création et activation de l’environnement virtuel

### Sous **Windows** (PowerShell)

```powershell
# Depuis le dossier racine du projet LABeCO2
py -3.11 -m venv .venv

# Activation de l’environnement virtuel
.\.venv\Scripts\Activate.ps1
```

> Si PowerShell bloque l'exécution des scripts, ajoute la ligne suivante temporairement :
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

---

### Sous **macOS** ou **Linux**

```bash
# Depuis le dossier racine du projet LABeCO2
python3.11 -m venv .venv

# Activation de l’environnement virtuel
source .venv/bin/activate
```

---

## 4. Installation des dépendances Python

### Sous **Windows** (PowerShell)

```powershell
python -m pip install --upgrade pip
python -m pip install -r .\installation\requirements.txt
```

---

### Sous **macOS** ou **Linux**

```bash
python -m pip install --upgrade pip
python -m pip install -r installation/requirements.txt
```

---

## 5. Installation des dépendances système (macOS/Linux uniquement)

Certaines bibliothèques Python comme PyTables ou PySide6 nécessitent des bibliothèques système préalables.

### Sous macOS :
```bash
brew install hdf5 qt c-blosc c-blosc2
```

### Sous Linux (Ubuntu) :
```bash
sudo apt install libhdf5-dev qtbase5-dev libblosc-dev
```

*Pas nécessaire sous Windows, les wheels pip contiennent les dépendances.*

---

## 6. Lancer l’application

```bash
python main.py
```

---

## 7. Désactivation et nettoyage

```bash
# Quitter l'environnement virtuel :
deactivate

# Supprimer un environnement virtuel :
rm -rf .venv        # ou : Remove-Item -Recurse -Force .venv (Windows PowerShell)
```

---

## Remarques

- Le fichier `requirements.txt` est universel, utilisable sur tous les systèmes avec `pip`.
- Les dépendances système doivent être installées séparément sur macOS/Linux.
- L'utilisation d’un environnement virtuel garantit un comportement stable et reproductible.
