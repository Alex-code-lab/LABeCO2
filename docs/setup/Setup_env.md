
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

5. **Créer un fichier `requirements.txt`** avec le contenu suivant :
   ```
   numpy==1.26.4
   pandas==2.2.2
   PySide6
   matplotlib==3.7.1
   adjustText==0.8
   ```

6. **Installer les packages à partir du fichier `requirements.txt`** :
   ```bash
   pip install -r requirements.txt
   ```

7. **Vérifier l'installation des packages** :
   ```bash
   pip show nom_du_package
   ```
   Remplacez `nom_du_package` par le nom du package que vous souhaitez vérifier.

8. **Exécuter votre script Python** :
   ```bash
   python ./main.py
   ```

En suivant ces étapes, vous créerez un environnement virtuel propre avec les versions spécifiques des packages nécessaires à votre projet. Le fichier `requirements.txt` facilite la gestion et le partage des dépendances de votre projet.


Pour générer une application, utiliser le fichier `.spec` de la plateforme :

```bash
pyinstaller LABeCO2_Mac.spec
# ou sous Windows :
pyinstaller LABeCO2_windows.spec
```
