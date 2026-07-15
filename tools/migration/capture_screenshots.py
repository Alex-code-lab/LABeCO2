# tools/migration/capture_screenshots.py
#
# Lance LABeCO2 et capture automatiquement tous les états + graphiques.
#
# Usage (depuis la racine du projet) :
#   python tools/migration/capture_screenshots.py
#
# Résultat : exports/screenshots/*.png

import sys
import os
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication, QComboBox
from PySide6.QtCore import QTimer

from ui.main_window import MainWindow
from utils.data_loader import resource_path

EXEMPLE_CSV = os.path.join(os.path.dirname(__file__), "exemple.csv")

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "exports", "screenshots")
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
    if all(c in df.columns for c in ('category', 'code_nacres', 'subsubcategory')):
        missing_code = (
            (df['category'] == 'Achats') &
            (df['code_nacres'].str.upper().isin(['NA', 'NAN', ''])) &
            (~df['subsubcategory'].str.upper().isin(['', 'NAN', 'NA']))
        )
        df.loc[missing_code, 'code_nacres'] = df.loc[missing_code, 'subsubcategory'].str[:4]
    for _, row in df.iterrows():
        window.create_or_update_history_item(row.to_dict())
    window.update_total_emissions()
    print(f"  → {len(df)} ligne(s) chargée(s) depuis exemple.csv")


# ─────────────────────────────────────────────────────────────────────────────
# Liste des graphiques à capturer
# (chart_type, nom_fichier, délai_ms avant capture — matplotlib est lent)
# ─────────────────────────────────────────────────────────────────────────────
CHARTS = [
    ("pie",                    "10_graphique_camembert.png",              1200),
    ("bar",                    "11_graphique_barres_prix_masse.png",      1200),
    ("proportional_bar",       "12_graphique_barres_prop.png",            1200),
    ("stacked_bar_consumables","13_graphique_barres_empilees.png",        1200),
    ("nacres_bar",             "14_graphique_nacres.png",                 1200),
    ("proportional_bar_mass",  "15_graphique_nacres_prop.png",            1200),
    ("pareto",                 "16_graphique_pareto.png",                 1200),
    ("transport",              "17_graphique_transport.png",              1200),
    ("transport_consumable",   "18_graphique_transport_consommable.png",  1200),
    ("transport_top",          "19_graphique_transport_top.png",          1200),
    ("transport_factor",       "20_graphique_transport_facteur.png",      1200),
    ("transport_scenario",     "21_graphique_transport_scenario.png",     1200),
    ("coverage",               "22_graphique_couverture.png",             1200),
    ("coverage_category",      "23_graphique_couverture_cat.png",         1200),
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
        scroll_area = window.centralWidget()
        sb = scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())
        save(window, "04_options_graphiques.png")
        window.toggle_graph_buttons_button.setChecked(False)
        sb.setValue(0)
        QTimer.singleShot(300, step9_sources)

    # ── Étape 9 : popup Sources ───────────────────────────────────────────────
    def step9_sources():
        def capture_and_close():
            # activeModalWidget ne dépend pas du focus OS (contrairement à
            # activeWindow, qui renvoie None si l'appli n'est pas au premier plan).
            popup = QApplication.activeModalWidget() or QApplication.activeWindow()
            if popup and popup is not window:
                save(popup, "05_sources.png")
                popup.close()
        QTimer.singleShot(600, capture_and_close)
        window.show_sources_popup("sources")        # bloquant — timer tourne dedans
        QTimer.singleShot(300, step10_methodo)

    # ── Étape 10 : popup Méthodologie ────────────────────────────────────────
    def step10_methodo():
        def capture_and_close():
            popup = QApplication.activeModalWidget() or QApplication.activeWindow()
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
        QTimer.singleShot(300, step14_open_machine)

    # ── Étape 14-15 : formulaire "Ajouter une machine" ───────────────────────
    def step14_open_machine():
        window.add_calcul_button.setChecked(True)
        window.category_combo.setCurrentText("Machine")
        QTimer.singleShot(400, step15_capture_machine)

    def step15_capture_machine():
        save(window, "09_ajout_machine.png")
        window.add_calcul_button.setChecked(False)
        window.category_combo.setCurrentText("Achats")
        QTimer.singleShot(300, lambda: step_chart(0))

    # ── Étapes graphiques : on itère sur la liste CHARTS ─────────────────────
    def step_chart(index):
        if index >= len(CHARTS):
            step24_edit_calcul()
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

    # ── Étape 24 : dialogue "Modifier un calcul" ─────────────────────────────
    def step24_edit_calcul():
        def capture_and_close():
            popup = QApplication.activeModalWidget() or QApplication.activeWindow()
            if popup is None or popup is window:
                print("  ✗  24_modifier_calcul.png  (dialogue introuvable)")
                return
            # Les combos aux libellés très longs (consommables) imposent une
            # largeur minimale de ~1900 px au dialogue. On plafonne leur
            # largeur (prise en compte dans le minimum du layout), puis on
            # efface le minimum que le layout a déjà figé sur le dialogue.
            # Le resize doit attendre le tick suivant, le temps que le layout
            # soit recalculé.
            for combo in popup.findChildren(QComboBox):
                if combo.sizeHint().width() > 600:
                    combo.setMaximumWidth(600)

            def resize_dialog():
                popup.setMinimumSize(0, 0)
                popup.resize(900, popup.sizeHint().height())

                def grab_and_close():
                    save(popup, "24_modifier_calcul.png")
                    popup.close()
                QTimer.singleShot(200, grab_and_close)
            QTimer.singleShot(200, resize_dialog)
        window.history_list.setCurrentCell(0, 0)
        QTimer.singleShot(1000, capture_and_close)
        window.modify_selected_calculation()        # bloquant — timer tourne dedans
        QTimer.singleShot(300, step25_manip_dialog)

    # ── Étape 25 : dialogue "Créer une manip type" ───────────────────────────
    def step25_manip_dialog():
        def capture_and_close():
            popup = QApplication.activeModalWidget() or QApplication.activeWindow()
            if popup and popup is not window:
                save(popup, "25_creer_manip_type.png")
                popup.close()
        QTimer.singleShot(1000, capture_and_close)
        window.define_user_manip_from_history()     # bloquant — timer tourne dedans
        QTimer.singleShot(300, step26_validation)

    # ── Étape 26 : fenêtre de validation (outil admin) ───────────────────────
    def step26_validation():
        import shutil
        import tempfile
        from ui.validate_window import ValidateWindow

        try:
            # Copie de la base de référence : la fenêtre ne doit pas toucher
            # le fichier suivi par git.
            src = os.path.join(PROJECT_ROOT, "data", "labeco2_reference.sqlite")
            tmp_db = os.path.join(tempfile.gettempdir(), "labeco2_capture_validation.sqlite")
            shutil.copyfile(src, tmp_db)
            vw = ValidateWindow(tmp_db, parent=window)
            # La base de référence n'a que des lignes "validated" : le filtre
            # par défaut ("À valider") afficherait un tableau vide.
            vw._widget.status_combo.setCurrentIndex(2)
            vw.show()
        except Exception as e:
            print(f"  ✗  26_validation.png  (erreur ouverture : {e})")
            QTimer.singleShot(200, finish)
            return

        def capture_and_close():
            save(vw, "26_validation.png")
            vw.close()
            QTimer.singleShot(300, finish)
        QTimer.singleShot(1200, capture_and_close)

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
    window.show()

    run(window)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
