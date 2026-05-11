# tools/capture_screenshots.py
#
# Lance LABeCO2, attend que la fenêtre soit prête, puis capture
# les écrans demandés en haute résolution dans exports/screenshots/.
#
# Usage :
#   cd /chemin/vers/LABeCO2
#   python tools/capture_screenshots.py
#
# Les captures sont sauvegardées dans exports/screenshots/

import sys
import os

# Rendre les imports du projet disponibles
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap

from ui.main_window import MainWindow
from utils.data_loader import resource_path

# ── Dossier de sortie ─────────────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "exports", "screenshots")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def save(widget, filename):
    """Capture un widget Qt et le sauvegarde en PNG haute résolution."""
    # grab() capture le widget tel qu'il est affiché, en résolution native
    # (Retina sur Mac = 2x, donc ~2000px de large si la fenêtre fait 1000px)
    pixmap = widget.grab()
    path = os.path.join(OUTPUT_DIR, filename)
    pixmap.save(path, "PNG")
    print(f"  ✓ {filename}  ({pixmap.width()}×{pixmap.height()} px)")


def run_captures(window):
    """Enchaîne toutes les captures. Appelé une fois la fenêtre affichée."""

    print("\nCaptures en cours...")

    # ── 1. Fenêtre principale ─────────────────────────────────────────────────
    save(window, "01_fenetre_principale.png")

    # ── 2. Onglets / zones spécifiques ───────────────────────────────────────
    # Si tu veux capturer un widget précis à l'intérieur de la fenêtre,
    # décommente et adapte les lignes ci-dessous.
    # Exemples :
    #
    #   save(window.tab_widget, "02_onglets.png")
    #   save(window.table_view, "03_tableau.png")
    #   save(window.results_panel, "04_resultats.png")
    #
    # Pour voir tous les attributs disponibles, tu peux faire :
    #   print(dir(window))

    # ── 3. Ouvrir un graphique et le capturer ─────────────────────────────────
    # Exemple : ouvrir le camembert et le capturer
    #
    #   window.generate_pie_chart()
    #   QApplication.processEvents()    # laisse Qt finir de dessiner
    #   if window.pie_chart_window:
    #       save(window.pie_chart_window, "05_camembert.png")

    print(f"\nTerminé. Fichiers dans : {os.path.abspath(OUTPUT_DIR)}\n")

    # Quitte l'appli après les captures
    QApplication.quit()


def main():
    app = QApplication(sys.argv)

    # Applique le vrai style de l'appli pour que les captures soient fidèles
    qss_path = resource_path(os.path.join("styles", "styles.qss"))
    if os.path.exists(qss_path):
        with open(qss_path) as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.showMaximized()   # plein écran pour plus de détail

    # QTimer.singleShot : exécute la fonction UNE FOIS après N millisecondes.
    # On attend 1500 ms pour que la fenêtre ait fini de se dessiner complètement
    # avant de lancer les captures.
    QTimer.singleShot(1500, lambda: run_captures(window))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
