# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# ui/charts/transport_factor_chart.py

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
    add_transport_summary,
    apply_transport_tight_layout,
    iter_transport_records,
    origin_color,
    set_vertical_text_room,
    short_origin_label,
    summarize_transport,
)

_COLOR_PCT = '#1a1a2e'   # texte pourcentage


class TransportFactorChartWindow(QDialog):
    """
    Émissions de transport par provenance.

    Pour chaque origine présente dans l'historique, affiche uniquement
    les émissions kg CO₂e dues au transport (masse × facteur de transport),
    ainsi que le pourcentage que cela représente par rapport aux émissions
    masse totales de chaque provenance.
    """

    finished = Signal()

    def __init__(self, main_window):
        super().__init__(parent=main_window)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self.main_window = main_window
        self.setWindowTitle("Émissions transport par provenance")
        self.setGeometry(300, 200, 860, 580)

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

        dm = self.main_window.data_manager
        records = list(iter_transport_records(self.main_window.history_list, dm))

        trans_by_origin = {}   # kg CO₂e transport uniquement
        total_by_origin = {}   # kg CO₂e émissions masse totales (pour le %)
        err_by_origin   = {}   # variance cumulée

        for record in records:
            origin = record["origin"]
            trans_by_origin[origin] = trans_by_origin.get(origin, 0.0) + record["transport_emissions"]
            total_by_origin[origin] = total_by_origin.get(origin, 0.0) + record["total_emissions"]
            err_by_origin[origin] = err_by_origin.get(origin, 0.0) + record["transport_error"] ** 2

        if not trans_by_origin:
            ax = self.figure.add_subplot(111)
            ax.text(
                0.5, 0.5,
                "Aucune donnée de masse disponible dans l'historique.",
                ha='center', va='center', transform=ax.transAxes
            )
            self.canvas.draw()
            return

        for k in err_by_origin:
            err_by_origin[k] = err_by_origin[k] ** 0.5

        # Tri décroissant sur les émissions transport
        origins = sorted(trans_by_origin, key=lambda o: trans_by_origin[o], reverse=True)
        self._plot(origins, trans_by_origin, total_by_origin, err_by_origin, dm, summarize_transport(records))

    # ------------------------------------------------------------------
    def _plot(self, origins, trans_dict, total_dict, err_dict, dm, summary):
        n = len(origins)
        x = np.arange(n)
        bar_w = 0.55

        trans_vals = np.array([trans_dict[o] for o in origins])
        total_vals = np.array([total_dict[o] for o in origins])
        errs       = np.array([err_dict[o]   for o in origins])
        pct_vals   = np.where(total_vals > 0, trans_vals / total_vals * 100, 0.0)

        ax = self.figure.add_subplot(111)

        bars = ax.bar(x, trans_vals, bar_w,
                      color=[origin_color(o) for o in origins], edgecolor='white')

        ax.errorbar(x, trans_vals, yerr=errs,
                    fmt='none', ecolor=COLOR_ERR, capsize=5, capthick=1, lw=0.8, zorder=5)

        max_val = trans_vals.max() if trans_vals.max() > 0 else 1.0
        peak = set_vertical_text_room(ax, trans_vals, errs, room_ratio=0.44)

        # Facteur de transport et pourcentage au-dessus de chaque barre
        for i, (orig, tv, pct, err) in enumerate(zip(origins, trans_vals, pct_vals, errs)):
            factor, _ = dm.get_transport_factor(orig)
            label = f"{pct:.0f}% du total masse\n({factor:.3f} kg CO₂e/kg)"
            ax.text(
                x[i],
                tv + err + peak * 0.035,
                label,
                ha='center',
                va='bottom',
                fontsize=7,
                color=_COLOR_PCT,
                clip_on=True,
            )

        # Valeur numérique à l'intérieur des barres (si assez hautes)
        for i, tv in enumerate(trans_vals):
            if tv > max_val * 0.08:
                ax.text(x[i], tv / 2, f"{tv:.1f}",
                        ha='center', va='center', fontsize=8,
                        color='white', fontweight='bold', clip_on=True)

        short_origins = [short_origin_label(o) for o in origins]
        ax.set_xticks(x)
        ax.set_xticklabels(short_origins, fontsize=8)
        for tick, origin in zip(ax.get_xticklabels(), origins):
            tick.set_color(origin_color(origin))
            tick.set_fontweight('bold')

        ax.set_ylabel("Émissions transport (kg CO₂e)", fontsize=9)
        ax.set_title(
            "Transport par provenance",
            fontsize=11,
            pad=14,
        )
        ax.set_xlim(-0.5, n - 0.5)
        ax.tick_params(axis='x', pad=6)

        legend_elements = [
            Patch(facecolor=origin_color(origin), label=origin)
            for origin in origins
        ]
        ax.legend(handles=legend_elements, title="Provenance", fontsize=8,
                  title_fontsize=8, framealpha=0.9, edgecolor='#cbd5e1',
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
