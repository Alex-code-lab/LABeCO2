import sys
import os
# from PyQt5.QtWidgets import QApplication
# from PyQt5.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from windows.main_window import MainWindow  # Importez la classe MainWindow
from utils.data_loader import resource_path

# Ajoute cette ligne pour spécifier le chemin des plugins Qt
os.environ["QT_PLUGIN_PATH"] = os.path.join(os.path.dirname(sys.executable), "PyQt5", "Qt5", "plugins")

# # Point d'entrée du programme
# if __name__ == '__main__':
#     app = QApplication(sys.argv)  # Crée une application PyQt

#      # Définir l'icône de l'application pour macOS (et autres plateformes)
#     script_dir = os.getcwd()  # Chemin vers le répertoire courant
#     icon_path = os.path.join(script_dir, 'images', 'icon.png')  # Chemin relatif vers le logo
#     app.setWindowIcon(QIcon(icon_path))  # Définir l'icône pour l'application entière

#     window = MainWindow()  # Crée la fenêtre principale
#     window.show()  # Affiche la fenêtre
#     app.exec()  # Lance la boucle d'événements

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
    sys.exit(app.exec())  # Lance la boucle d'événements