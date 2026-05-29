# SPDX-License-Identifier: GPL-3.0-or-later
# main.py, LABeCO2 ©
# Copyright (c), 2024-2026, LABeCO2, Alexandre Souchaud. Tous droits réservés.
# Auteur : Alexandre Souchaud — labeco2.contact@gmail.com
#
# Ce programme est distribué sous licence :
#   - GNU GPL v3 (ou toute version ultérieure), pour une utilisation libre et non commerciale ;
#
# Vous pouvez consulter la GPL ici : https://www.gnu.org/licenses/gpl-3.0.fr.html
#
# Date de création : 01/10/2024 — Version V3.0 du 28/05/2026
# DOI: 10.5281/zenodo.15240634
# Ce fichier est le point d'entrée de l'application PySide6.
import sys
import os
import traceback
import multiprocessing
import logging

from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt

from ui.main_window import MainWindow
from utils.data_loader import resource_path

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    logger.info("Démarrage de l'application LABeCO2")
    try:
        app = QApplication(sys.argv)
        logger.info("QApplication créée")

        # Splash screen
        splash = None
        try:
            splash_pix = QPixmap(resource_path(os.path.join("assets", "Logo.png")))
            splash = QSplashScreen(splash_pix)
            splash.setWindowFlag(Qt.FramelessWindowHint)
            splash.showMessage("Chargement de LABeCO2...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
            splash.show()
            app.processEvents()
            logger.info("SplashScreen affiché")
        except Exception as e:
            logger.warning("Erreur lors du splashscreen : %s", e)

        # Appliquer le style QSS
        try:
            qss_path = resource_path(os.path.join("styles", "styles.qss"))
            if os.path.exists(qss_path):
                with open(qss_path, "r", encoding="utf-8") as f:
                    app.setStyleSheet(f.read())
                logger.info("QSS appliqué")
        except Exception as e:
            logger.warning("Erreur QSS : %s", e)

        # Appliquer l'icône
        try:
            icon_path = resource_path(os.path.join("assets", "icon.icns"))
            if os.path.exists(icon_path):
                app.setWindowIcon(QIcon(icon_path))
                logger.info("Icône appliquée")
        except Exception as e:
            logger.warning("Erreur icône : %s", e)

        # Créer la fenêtre principale
        try:
            logger.info("Création de MainWindow")
            window = MainWindow()
            window.show()
            if splash:
                splash.finish(window)
            window.raise_()
            window.activateWindow()
            logger.info("MainWindow affichée")
            return app.exec()
        except Exception as e:
            logger.exception("Erreur dans MainWindow : %s", e)
            return 1

    except Exception as e:
        logger.exception("Erreur globale : %s", e)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        sys.exit(main())
    except Exception:
        logger.exception("Erreur globale non interceptée")
        sys.exit(1)
