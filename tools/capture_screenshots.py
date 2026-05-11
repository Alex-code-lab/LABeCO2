# tools/capture_screenshots.py
#
# Lance LABeCO2 et capture automatiquement tous les états + graphiques.
#
# Usage (depuis la racine du projet) :
#   python tools/capture_screenshots.py
#
# Résultat : exports/screenshots/*.png

import sys
import os
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from ui.main_window import MainWindow
from utils.data_loader import resource_path

EXEMPLE_CSV = os.path.join(os.path.dirname(__file__), "exemple.csv")

OUTPUT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "exports", "screenshots")
)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def save(widget, filename):
    path = os.path.join(OUTPUT_DIR, filename)
    pixmap = widget.grab()
    pixmap.save(path, "PNG")
    print(f"  ✓  {filename}  ({pixmap.width()}×{pixmap.height()} px)")


def load_exemple(window):
    """Injecte exemple.csv dans l'historique sans passer par le dialogue fichier."""
    df = pd.read_csv(EXEMPLE_CSV, sep=';', keep_default_na=False)
    for col in ["value", "quantity", "days", "emissions_price", "emission_mass", "total_mass"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    for col in ["category", "subcategory", "subsubcategory", "name",
                "code_nacres", "consommable", "unit"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    for col in ["code_nacres", "consommable"]:
        if col in df.columns:
            df[col] = df[col].replace({'nan': 'NA', 'none': 'NA', 'None': 'NA', '': 'NA'})
    for col in ["name", "subsubcategory"]:
        if col in df.columns:
            df[col] = df[col].replace({'nan': '', 'none': '', 'None': ''})
    for _, row in df.iterrows():
        window.create_or_update_history_item(row.to_dict())
    window.update_total_emissions()
    print(f"  → {len(df)} ligne(s) chargée(s) depuis exemple.csv")


# ─────────────────────────────────────────────────────────────────────────────
# Liste des graphiques à capturer
# (chart_type, nom_fichier, délai_ms avant capture — matplotlib est lent)
# ─────────────────────────────────────────────────────────────────────────────
CHARTS = [
    ("pie",                    "09_graphique_camembert.png",          1200),
    ("bar",                    "10_graphique_barres_prix_masse.png",   1200),
    ("proportional_bar",       "11_graphique_barres_prop.png",         1200),
    ("stacked_bar_consumables","12_graphique_barres_empilees.png",     1200),
    ("nacres_bar",             "13_graphique_nacres.png",              1200),
    ("proportional_bar_mass",  "14_graphique_nacres_prop.png",         1200),
    ("pareto",                 "15_graphique_pareto.png",              1200),
    ("transport",              "16_graphique_transport.png",           1200),
    ("coverage",               "17_graphique_couverture.png",          1200),
    ("coverage_category",      "18_graphique_couverture_cat.png",      1200),
]


def run(window):

    # ── Étape 1 : démarrage vide ──────────────────────────────────────────────
    def step1_demarrage():
        save(window, "01_demarrage.png")
        QTimer.singleShot(300, step2_load)

    # ── Étape 2 : chargement de l'exemple ────────────────────────────────────
    def step2_load():
        load_exemple(window)
        QTimer.singleShot(400, step3_open_calcul)

    # ── Étape 3-4 : "Ajouter un calcul" ──────────────────────────────────────
    def step3_open_calcul():
        window.add_calcul_button.setChecked(True)
        QTimer.singleShot(400, step4_capture_calcul)

    def step4_capture_calcul():
        save(window, "02_ajouter_calcul.png")
        QTimer.singleShot(300, step5_open_manip)

    # ── Étape 5-6 : "Ajouter une manip type" ─────────────────────────────────
    def step5_open_manip():
        window.add_calcul_button.setChecked(False)
        window.add_manip_button.setChecked(True)
        QTimer.singleShot(400, step6_capture_manip)

    def step6_capture_manip():
        save(window, "03_manip_type.png")
        QTimer.singleShot(300, step7_open_graph)

    # ── Étape 7-8 : "Options graphiques" ─────────────────────────────────────
    def step7_open_graph():
        window.add_manip_button.setChecked(False)
        window.toggle_graph_buttons_button.setChecked(True)
        QTimer.singleShot(400, step8_capture_graph)

    def step8_capture_graph():
        save(window, "04_options_graphiques.png")
        window.toggle_graph_buttons_button.setChecked(False)
        QTimer.singleShot(300, step9_sources)

    # ── Étape 9 : popup Sources ───────────────────────────────────────────────
    def step9_sources():
        def capture_and_close():
            popup = QApplication.activeWindow()
            if popup and popup is not window:
                save(popup, "05_sources.png")
                popup.close()
        QTimer.singleShot(600, capture_and_close)
        window.show_sources_popup("sources")        # bloquant — timer tourne dedans
        QTimer.singleShot(300, step10_methodo)

    # ── Étape 10 : popup Méthodologie ────────────────────────────────────────
    def step10_methodo():
        def capture_and_close():
            popup = QApplication.activeWindow()
            if popup and popup is not window:
                save(popup, "06_methodologie.png")
                popup.close()
        QTimer.singleShot(600, capture_and_close)
        window.show_methodology_popup()             # bloquant — timer tourne dedans
        QTimer.singleShot(300, step11_consommable)

    # ── Étape 11-12 : "Ajouter un consommable" ───────────────────────────────
    def step11_consommable():
        window.open_data_mass_window_new()
        QTimer.singleShot(800, step12_capture_consommable)

    def step12_capture_consommable():
        dmw = window.data_mass_window
        if dmw and dmw.isVisible():
            save(dmw, "07_ajouter_consommable.png")
            dmw.close()
        else:
            print("  ✗  data_mass_window non trouvée")
        QTimer.singleShot(300, step13_fenetre_avec_donnees)

    # ── Étape 13 : fenêtre principale avec données (vue d'ensemble) ──────────
    def step13_fenetre_avec_donnees():
        save(window, "08_fenetre_avec_donnees.png")
        QTimer.singleShot(300, lambda: step_chart(0))

    # ── Étapes graphiques : on itère sur la liste CHARTS ─────────────────────
    def step_chart(index):
        if index >= len(CHARTS):
            finish()
            return

        chart_type, filename, delay = CHARTS[index]

        def open_and_schedule():
            try:
                window.generate_chart(chart_type)
            except Exception as e:
                print(f"  ✗  {filename}  (erreur ouverture : {e})")
                QTimer.singleShot(200, lambda: step_chart(index + 1))
                return
            QTimer.singleShot(delay, lambda: capture_chart(index, chart_type, filename))

        def capture_chart(idx, ctype, fname):
            attr = f"{ctype}_chart_window"
            chart_win = getattr(window, attr, None)
            if chart_win and chart_win.isVisible():
                save(chart_win, fname)
                chart_win.close()
            else:
                print(f"  ✗  {fname}  (fenêtre introuvable)")
            QTimer.singleShot(400, lambda: step_chart(idx + 1))

        open_and_schedule()

    # ── Fin ───────────────────────────────────────────────────────────────────
    def finish():
        print(f"\nTerminé — fichiers dans :\n  {OUTPUT_DIR}\n")
        QApplication.quit()

    # Démarre après 1,5 s (laisse la fenêtre finir de s'afficher)
    QTimer.singleShot(1500, step1_demarrage)


def main():
    app = QApplication(sys.argv)

    qss_path = resource_path(os.path.join("styles", "styles.qss"))
    if os.path.exists(qss_path):
        with open(qss_path) as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.showMaximized()

    run(window)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
