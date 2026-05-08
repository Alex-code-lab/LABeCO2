# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# ui/charts/pareto_chart.py

import numpy as np
import matplotlib
matplotlib.use('QtAgg')
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFileDialog, QToolBar, QStyle, QMessageBox
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, Signal
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from ui.charts.history_utils import iter_history_data

_COLOR_HIGH = '#e05252'   # postes dans les 80 %
_COLOR_LOW  = '#73c2fb'   # postes au-delà
_COLOR_LINE = '#1a1a2e'   # courbe cumulée


class ParetoChartWindow(QDialog):
    """
    Diagramme de Pareto des émissions CO₂e.

    Barres horizontales triées par valeur décroissante + courbe cumulée en %,
    avec ligne de seuil à 80 %.
    """

    finished = Signal()

    def __init__(self, main_window):
        super().__init__(parent=main_window)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self.main_window = main_window
        self.setWindowTitle("Pareto des émissions")
        self.setGeometry(300, 200, 950, 680)

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)

        toolbar = QToolBar()
        save_icon = self.style().standardIcon(QStyle.SP_DialogSaveButton)
        save_action = QAction(save_icon, "", self)
        save_action.setToolTip("Enregistrer l'image")
        save_action.triggered.connect(self.save_image)
        toolbar.addAction(save_action)

        refresh_icon = self.style().standardIcon(QStyle.SP_BrowserReload)
        refresh_action = QAction(refresh_icon, "", self)
        refresh_action.setToolTip("Actualiser le graphique")
        refresh_action.triggered.connect(self.refresh_data)
        toolbar.addAction(refresh_action)

        layout = QVBoxLayout()
        layout.addWidget(toolbar)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

        self.refresh_data()
        self.main_window.data_changed.connect(self.refresh_data)

    # ------------------------------------------------------------------
    @staticmethod
    def _clean(value):
        """Retourne une chaîne propre, ou '' si la valeur est nan/NA/None/vide."""
        if value is None:
            return ''
        s = str(value).strip()
        return '' if s.lower() in ('nan', 'na', 'n/a', 'none') else s

    def _nacres_desc(self, code_nacres, prefix):
        """
        Retourne la description lisible d'un code NACRES.
        Cherche d'abord dans code_nacres lui-même (format "CODE - DESC"),
        puis dans la table principale (subsubcategory == prefix → name).
        """
        # Cas 1 : description déjà dans la chaîne ("IE01 - APPAREILS DE PRODUCTION...")
        if ' - ' in code_nacres:
            raw = code_nacres.split(' - ', 1)[1].strip()
            return raw.title() if raw else ''

        # Cas 2 : recherche dans self.main_window.data
        try:
            df = self.main_window.data
            mask = (
                (df['category'] == 'Achats') &
                (df['subsubcategory'].fillna('').astype(str).str.strip().str.upper() == prefix.upper())
            )
            hits = df[mask]['name'].dropna()
            if not hits.empty:
                raw = str(hits.iloc[0]).strip()
                return raw.title() if raw else ''
        except Exception:
            pass
        return ''

    def _build_label(self, data):
        """
        Étiquette courte et distinctive.
        - Achats consommable : "[CODE] nom_consommable"
        - Autres : "Catégorie / Nom"
        """
        category    = self._clean(data.get('category', ''))
        subcategory = self._clean(data.get('subcategory', ''))
        name        = self._clean(data.get('name', ''))
        consommable = self._clean(data.get('consommable', ''))
        code_nacres = self._clean(data.get('code_nacres', ''))

        if category == 'Achats':
            prefix = code_nacres[:4] if code_nacres else ''
            if consommable:
                return f"[{prefix}] {consommable}" if prefix else consommable
            if prefix:
                desc = self._nacres_desc(code_nacres, prefix)
                desc_short = desc if len(desc) <= 30 else desc[:29] + '…'
                return f"[{prefix}] {desc_short}" if desc_short else f"[{prefix}]"

        # Pour les autres catégories : catégorie + nom ou sous-catégorie
        if name and name not in (category, subcategory):
            return f"{category} / {name}" if category else name
        if subcategory and subcategory != category:
            subcat_short = subcategory if len(subcategory) <= 28 else subcategory[:27] + '…'
            return f"{category} / {subcat_short}" if category else subcat_short
        return category or "?"

    # ------------------------------------------------------------------
    def refresh_data(self):
        self.figure.clear()

        aggregated = {}
        for data in iter_history_data(self.main_window.history_list):
            label = self._build_label(data)
            ep = float(data.get('emissions_price', 0.0) or 0.0)
            aggregated[label] = aggregated.get(label, 0.0) + ep

        aggregated = {k: v for k, v in aggregated.items() if v > 0}

        if not aggregated:
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, "Aucune donnée disponible.",
                    ha='center', va='center', transform=ax.transAxes)
            self.canvas.draw()
            return

        self._plot(aggregated)

    # ------------------------------------------------------------------
    def _plot(self, aggregated):
        sorted_items = sorted(aggregated.items(), key=lambda x: x[1], reverse=True)
        labels = [it[0] for it in sorted_items]
        values = np.array([it[1] for it in sorted_items])

        total = values.sum()
        cumulative_pct = np.cumsum(values) / total * 100

        n = len(labels)
        y_pos = np.arange(n)

        threshold_idx = next((i for i, c in enumerate(cumulative_pct) if c >= 80), n - 1)
        colors = [_COLOR_HIGH if i <= threshold_idx else _COLOR_LOW for i in range(n)]

        ax1 = self.figure.add_subplot(111)
        ax2 = ax1.twiny()

        # ── Barres ──────────────────────────────────────────────────────
        bars = ax1.barh(y_pos, values, color=colors, edgecolor='white', height=0.6)

        for bar, val in zip(bars, values):
            if val > 0:
                ax1.text(
                    bar.get_width() + total * 0.005,
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:.1f}",
                    va='center', ha='left', fontsize=7, color='#374151'
                )

        # ── Courbe cumulée ───────────────────────────────────────────────
        ax2.plot(cumulative_pct, y_pos, color=_COLOR_LINE, marker='o',
                 markersize=3, linewidth=1.5, zorder=5)

        ax2.axvline(x=80, color=_COLOR_HIGH, linestyle='--', linewidth=1, alpha=0.7)
        ax2.text(80.5, n - 0.5, '80 %', color=_COLOR_HIGH, fontsize=8, va='top')

        # ── Axe Y ────────────────────────────────────────────────────────
        ax1.set_yticks(y_pos)
        max_chars = 38
        short_labels = [
            (lbl if len(lbl) <= max_chars else lbl[:max_chars - 1] + '…')
            for lbl in labels
        ]
        ax1.set_yticklabels(short_labels, fontsize=8)
        ax1.invert_yaxis()

        # ── Axes X avec couleurs distinctes ─────────────────────────────
        ax1.set_xlabel("Émissions (kg CO₂e)", fontsize=9, color='#374151')
        ax1.tick_params(axis='x', colors='#374151')
        ax1.spines['bottom'].set_color('#374151')

        ax2.set_xlabel("Cumul (%)", fontsize=9, color=_COLOR_LINE, labelpad=6)
        ax2.tick_params(axis='x', colors=_COLOR_LINE)
        ax2.spines['top'].set_color(_COLOR_LINE)
        ax2.set_xlim(0, 105)

        ax1.set_title("Diagramme de Pareto des émissions CO₂e", fontsize=11, pad=32)

        # ── Légende ──────────────────────────────────────────────────────
        legend_elements = [
            Patch(facecolor=_COLOR_HIGH, label='Postes ≤ 80 % cumulés'),
            Patch(facecolor=_COLOR_LOW,  label='Postes > 80 % cumulés'),
            Line2D([0], [0], color=_COLOR_LINE, marker='o', markersize=4,
                   linewidth=1.5, label='% cumulé (axe haut)'),
        ]
        ax1.legend(handles=legend_elements, loc='lower right', fontsize=8,
                   framealpha=0.9, edgecolor='#cbd5e1')

        self.figure.tight_layout()
        self.canvas.draw()

    # ------------------------------------------------------------------
    def save_image(self):
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer l'image", "",
            "Images PNG (*.png);;Images JPEG (*.jpg *.jpeg);;Fichiers PDF (*.pdf);;Tous les fichiers (*)"
        )
        if file_name:
            if not any(file_name.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.pdf']):
                file_name += '.png'
            try:
                self.figure.savefig(file_name)
                QMessageBox.information(self, 'Succès', f'Image enregistrée dans {file_name}')
            except Exception as e:
                QMessageBox.warning(self, 'Erreur', f'Erreur lors de l\'enregistrement : {e}')
        else:
            QMessageBox.information(self, 'Annulation', 'Enregistrement annulé.')

    def closeEvent(self, event):
        self.finished.emit()
        super().closeEvent(event)
