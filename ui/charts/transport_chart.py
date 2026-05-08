# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# ui/charts/transport_chart.py

import numpy as np
import matplotlib
matplotlib.use('QtAgg')
from matplotlib.patches import Patch

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFileDialog, QToolBar, QStyle, QMessageBox
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, Signal
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from ui.charts.transport_utils import (
    COLOR_ERR,
    COLOR_MATERIAL,
    COLOR_TRANSPORT,
    add_transport_summary,
    apply_transport_tight_layout,
    iter_transport_records,
    origin_color,
    set_vertical_text_room,
    short_origin_label,
    summarize_transport,
)


class TransportChartWindow(QDialog):
    """
    Graphique des émissions masse par provenance.

    Pour chaque origine géographique présente dans l'historique,
    affiche les émissions kg CO₂e décomposées en :
      - part matière (fabrication du consommable)
      - part transport (acheminement selon la provenance)
    """

    finished = Signal()

    def __init__(self, main_window):
        super().__init__(parent=main_window)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self.main_window = main_window
        self.setWindowTitle("Impact du transport par provenance")
        self.setGeometry(300, 200, 900, 620)

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
    def refresh_data(self):
        self.figure.clear()

        records = list(iter_transport_records(
            self.main_window.history_list,
            self.main_window.data_manager,
        ))

        if not records:
            ax = self.figure.add_subplot(111)
            ax.text(
                0.5, 0.5,
                "Aucune donnée de masse disponible dans l'historique.",
                ha='center', va='center', transform=ax.transAxes
            )
            self.canvas.draw()
            return

        mat_by_origin = {}
        trans_by_origin = {}
        err_by_origin = {}

        for record in records:
            origin = record["origin"]
            mat_by_origin[origin] = mat_by_origin.get(origin, 0.0) + record["material_emissions"]
            trans_by_origin[origin] = trans_by_origin.get(origin, 0.0) + record["transport_emissions"]
            err_by_origin[origin] = err_by_origin.get(origin, 0.0) + record["emission_error"] ** 2

        for origin in err_by_origin:
            err_by_origin[origin] = err_by_origin[origin] ** 0.5

        # Trier par émissions totales décroissantes
        origins = sorted(
            mat_by_origin.keys(),
            key=lambda o: mat_by_origin[o] + trans_by_origin[o],
            reverse=True
        )

        self._plot(origins, mat_by_origin, trans_by_origin, err_by_origin, summarize_transport(records))

    # ------------------------------------------------------------------
    def _plot(self, origins, mat_dict, trans_dict, err_dict, summary):
        n = len(origins)
        x = np.arange(n)
        bar_w = 0.55

        mat_vals   = np.array([mat_dict[o]   for o in origins])
        trans_vals = np.array([trans_dict[o] for o in origins])
        totals     = mat_vals + trans_vals
        errs       = np.array([err_dict[o]   for o in origins])
        origin_colors = [origin_color(o) for o in origins]

        ax = self.figure.add_subplot(111)

        bars_mat   = ax.bar(x, mat_vals,   bar_w,
                            color=COLOR_MATERIAL,  edgecolor=origin_colors,
                            linewidth=1.2, label='Matière')
        bars_trans = ax.bar(x, trans_vals, bar_w,
                            bottom=mat_vals,
                            color=COLOR_TRANSPORT, edgecolor=origin_colors,
                            linewidth=1.2, label='Transport')

        # Barres d'erreur sur le total
        ax.errorbar(x, totals, yerr=errs,
                    fmt='none', ecolor=COLOR_ERR, capsize=5, capthick=1, lw=0.8, zorder=5)

        peak = set_vertical_text_room(ax, totals, errs, room_ratio=0.42)

        # Pourcentage transport au-dessus de chaque barre
        for i, (tot, tr) in enumerate(zip(totals, trans_vals)):
            if tot > 0:
                pct = tr / tot * 100
                ax.text(x[i], tot + errs[i] + peak * 0.035,
                        f"{pct:.0f}%\ntransport",
                        ha='center', va='bottom', fontsize=7, color=COLOR_ERR,
                        clip_on=True)

        # Valeurs numériques à l'intérieur des barres (si assez hautes)
        for i, (mv, tv) in enumerate(zip(mat_vals, trans_vals)):
            if mv > totals.max() * 0.06:
                ax.text(x[i], mv / 2,
                        f"{mv:.1f}", ha='center', va='center', fontsize=7,
                        color='white', clip_on=True)
            if tv > totals.max() * 0.06:
                ax.text(x[i], mv + tv / 2,
                        f"{tv:.1f}", ha='center', va='center', fontsize=7,
                        color='white', clip_on=True)

        # Étiquettes axe X : nom provenance sur deux lignes si nécessaire
        short_origins = [short_origin_label(o) for o in origins]
        ax.set_xticks(x)
        ax.set_xticklabels(short_origins, fontsize=8)
        for tick, origin in zip(ax.get_xticklabels(), origins):
            tick.set_color(origin_color(origin))
            tick.set_fontweight('bold')

        ax.set_ylabel("Émissions (kg CO₂e)", fontsize=9)
        ax.set_title(
            "Par provenance : matière et transport",
            fontsize=11,
            pad=14,
        )
        ax.set_xlim(-0.5, n - 0.5)
        ax.tick_params(axis='x', pad=6)

        legend_elements = [
            Patch(facecolor=COLOR_MATERIAL, label='Émissions matière'),
            Patch(facecolor=COLOR_TRANSPORT, label='Émissions transport'),
        ]
        legend_elements.extend(
            Patch(facecolor=origin_color(origin), label=origin)
            for origin in origins
        )
        ax.legend(handles=legend_elements, fontsize=8,
                  framealpha=0.9, edgecolor='#cbd5e1',
                  loc='center right', bbox_to_anchor=(0.985, 0.46),
                  bbox_transform=self.figure.transFigure)

        add_transport_summary(self.figure, summary)
        apply_transport_tight_layout(self.figure, rect=(0, 0, 0.76, 0.86))
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
