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
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from windows.main_window import MainWindow  # Importez la classe MainWindow
from utils.data_loader import resource_path

# # Ajoute cette ligne pour spécifier le chemin des plugins Qt
# os.environ["QT_PLUGIN_PATH"] = os.path.join(os.path.dirname(sys.executable), "PyQt5", "Qt5", "plugins")

# Point d'entrée du programme
if __name__ == '__main__':
    app = QApplication(sys.argv)  # Crée une application PySide6

    # Charger le QSS depuis le fichier externe
    qss_path = resource_path(os.path.join('styles', 'styles.qss'))
    if os.path.exists(qss_path):
        with open(qss_path, "r") as f:
            app.setStyleSheet(f.read())
    else:
        print(f"Fichier QSS non trouvé à l'emplacement : {qss_path}")

    # Définir l'icône de l'application pour macOS (et autres plateformes)
    icon_path = resource_path(os.path.join('images', 'icon.icns'))  # Utilisez .icns pour macOS
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))  # Définir l'icône pour l'application entière
    else:
        print(f"Fichier d'icône non trouvé à l'emplacement : {icon_path}")

    window = MainWindow()  # Crée la fenêtre principale
    window.show()  # Affiche la fenêtre
    # for w in QApplication.topLevelWidgets():
    #     print(w, w.windowTitle(), w.isVisible())
    sys.exit(app.exec())  # Lance la boucle d'événements