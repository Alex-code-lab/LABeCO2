# SPDX-License-Identifier: GPL-3.0-or-late
# main.py, LABeCO2 ©
# Copyright (c), 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
# Auteur : Alexandre Souchaud — labeco2.contact@gmail.com
#
# Ce programme est distribué sous  licence :
#   - GNU GPL v3 (ou toute version ultérieure), pour une utilisation libre et non commerciale ;
#
# Vous pouvez consulter la GPL ici : https://www.gnu.org/licenses/gpl-3.0.fr.html
#
# Date de création : 01/10/2024 — Version V2.0 du 10/04/2025
# DOI: 10.5281/zenodo.15243498
# Ce fichier est le point d'entrée de l'application PySide6.
import sys
import os
import traceback
import multiprocessing

from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt

from windows.main_window import MainWindow
from utils.data_loader import resource_path

def main():
    print("\n===== Démarrage de l'application LABeCO2 =====")
    try:
        app = QApplication(sys.argv)
        print("QApplication créée")

        # Splash screen
        try:
            splash_pix = QPixmap(resource_path(os.path.join("images", "Logo.png")))
            splash = QSplashScreen(splash_pix)
            splash.setWindowFlag(Qt.FramelessWindowHint)
            splash.showMessage("Chargement de LABeCO2...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
            splash.show()
            app.processEvents()
            print("SplashScreen affiché")
        except Exception as e:
            print("Erreur lors du splashscreen :", e)

        # Appliquer le style QSS
        try:
            qss_path = resource_path(os.path.join("styles", "styles.qss"))
            print(f"Chargement QSS : {qss_path}")
            if os.path.exists(qss_path):
                with open(qss_path, "r") as f:
                    app.setStyleSheet(f.read())
                print("QSS appliqué")
            else:
                print("Fichier QSS non trouvé.")
        except Exception as e:
            print("Erreur QSS :", e)

        # Appliquer l'icône
        try:
            icon_path = resource_path(os.path.join("images", "icon.icns"))
            print(f"Chargement icône : {icon_path}")
            if os.path.exists(icon_path):
                app.setWindowIcon(QIcon(icon_path))
                print("Icône appliquée")
            else:
                print("Fichier icône non trouvé.")
        except Exception as e:
            print("Erreur icône :", e)

        # Créer la fenêtre principale
        try:
            print("Création de MainWindow…")
            window = MainWindow()
            window.show()
            splash.finish(window)
            print("MainWindow affichée")
            sys.exit(app.exec())
        except Exception as e:
            print("Erreur dans MainWindow :", e)
            traceback.print_exc()
            input("Appuyez sur Entrée pour quitter...")
            sys.exit(1)

    except Exception as e:
        print("Erreur globale :", e)
        traceback.print_exc()
        input("Appuyez sur Entrée pour quitter...")

if __name__ == "__main__":
    # Nécessaire pour les exécutables PyInstaller qui utilisent multiprocessing
    multiprocessing.freeze_support()

    try:
        main()
    except Exception:
        print("\nErreur globale :")
        traceback.print_exc()
        input("Appuyez sur Entrée pour quitter…")