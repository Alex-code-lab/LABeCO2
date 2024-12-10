

# Trouver la librairie libpython3.11
find / -name libpython3.11.dylib 2>/dev/null
# Sortie attendue ; 
/Users/souchaud/anaconda3/lib/libpython3.11.dylib

# ajout dans le fichier main.spec 
binaries = [
    ('/Users/souchaud/anaconda3/lib/libpython3.11.dylib', 'Contents/Frameworks/')
],    binaries=binaries,  # Ajout des bibliothèques


# On peut executer puinstaller avec le debug
pyinstaller --debug=all main.py

# On ajoute éventuellement toutes les dépendances manquantes.
hiddenimports = ['nom_de_la_dependance1', 'nom_de_la_dependance2']

# Si des modules spécifiques ne sont pas collectés : 
pyinstaller --collect-all nom_du_module main.py

# pour étudier les dépendances de l'app qui a été créé.
otool -L /Users/souchaud/Desktop/dev_appli/dist/LABeCO2.app/Contents/MacOS/LABeCO2 