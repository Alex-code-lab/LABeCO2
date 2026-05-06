
Pour configurer un environnement Python propre avec des versions spécifiques de packages, suivez les étapes ci-dessous :

1. **Installer Python 3.11** :
   ```bash
   brew install python@3.11
   ```

2. **Créer un environnement virtuel** :
   ```bash
   python3.11 -m venv LABeCO2_env311
   ```

3. **Activer l'environnement virtuel** :
   ```bash
   source LABeCO2_env311/bin/activate
   ```

4. **Mettre à jour pip** :
   ```bash
   pip install --upgrade pip
   ```

5. **Installer HDF5** (nécessaire pour le package `tables`) :
   ```bash
   brew install hdf5
   ```

6. **Créer un fichier `requirements.txt`** avec le contenu suivant :
   ```
   scipy==1.10.1
   pyinstaller==5.13.2
   pyinstaller-hooks-contrib==2023.8
   pyside6==6.5.2
   matplotlib==3.7.2
   adjustText==0.8
   numpy==1.25.2
   pandas==2.0.3
   tables==3.9.0
   ```

7. **Installer les packages à partir du fichier `requirements.txt`** :
   ```bash
   pip install -r requirements.txt
   ```

8. **Vérifier l'installation des packages** :
   ```bash
   pip show nom_du_package
   ```
   Remplacez `nom_du_package` par le nom du package que vous souhaitez vérifier.

9. **Exécuter votre script Python** :
   ```bash
   python ./main.py
   ```

En suivant ces étapes, vous créerez un environnement virtuel propre avec les versions spécifiques des packages nécessaires à votre projet. Le fichier `requirements.txt` facilite la gestion et le partage des dépendances de votre projet.


Pour en faire une application export HDF5_DIR=/opt/homebrew
pyinstaller main.spec