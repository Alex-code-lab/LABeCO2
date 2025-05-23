
Bonnes pratiques Git pour ton projet
=====================================

Initialisation
--------------
- Crée un repository Git local :
  git init
- Associe ton repository local à un repository distant sur GitHub :
  git remote add origin https://github.com/ton-nom-utilisateur/nom-du-repository.git
- Ajoute et commite les fichiers initiaux :
  git add .
  git commit -m "Initial commit"
- Pousse les modifications vers le repository distant :
  git branch -M main
  git push -u origin main

Utilisation d'un fichier .gitignore
-----------------------------------
- Crée un fichier nommé .gitignore à la racine de ton projet.
- Ajoute les fichiers ou dossiers que tu ne veux pas suivre avec Git. Exemples :
  - __pycache__/ : pour ignorer les fichiers Python compilés.
  - *.log : pour ignorer tous les fichiers log.
  - .env : pour ignorer les fichiers contenant des informations sensibles, comme les clés API ou les mots de passe.
  - venv/ : pour ignorer les environnements virtuels Python.
- Commits tes modifications au fichier .gitignore :
  git add .gitignore
  git commit -m "Ajout d'un fichier .gitignore pour exclure des fichiers inutiles"
- Si déjà commit mais qu'on veut enlever : 
  git rm -r --cached "nom a enlever"
  Git add ...
  Git commit -m ...
  Git push 

Gestion des commits
-------------------
- Fais des commits fréquents pour enregistrer l'évolution de ton travail.
- Utilise des messages clairs et descriptifs :
  git commit -m "Description concise des modifications"
- Ne commite pas de fichiers inutiles (ex. : fichiers temporaires, binaires).
  Configure un fichier .gitignore pour exclure ces fichiers.

Travail en branches
--------------------
- Travaille toujours sur une branche différente de "main" pour les nouvelles fonctionnalités ou corrections de bugs :
  git checkout -b ma-nouvelle-branche
  ensuite git add . / git commit -m ..
  puis:
- Une fois le travail terminé, pousse la branche vers le repository distant :
  git push --set-upstream origin nom-de-la-branche
  ça établi un lien direct encore le local et le distant vers la nouvelle branche
  ça sera toujours sur cette nouvelle branche
- Une fois le travail terminé, fusionne la branche dans "main" avec un merge :
  git merge ma-nouvelle-branche
- Supprime les branches obsolètes après fusion :
  git branch -d ma-nouvelle-branche

Synchronisation avec GitHub
---------------------------
- Récupère toujours les modifications du repository distant avant de commencer à travailler :
  git pull
- Pousse régulièrement ton travail vers le repository distant :
  git push

Collaboration (si applicable)
------------------------------
- Utilise des pull requests (PR) pour soumettre et examiner les modifications avant de les fusionner.
- Ajoute des reviewers pour une vérification du code.

Sauvegarde et historique
------------------------
- Si tu fais une erreur, utilise Git pour annuler ou revenir à une version précédente :
  - Pour annuler des modifications non commitées, utilise :
    git checkout -- nom-du-fichier
  - Pour réinitialiser complètement ton dépôt à un état précédent :
    git reset --hard ID_du_commit
  - Attention : git reset --hard supprime définitivement les modifications non commitées.

Astuce supplémentaire
----------------------
- Évite de travailler directement sur la branche "main" pour minimiser les risques d'erreurs.
