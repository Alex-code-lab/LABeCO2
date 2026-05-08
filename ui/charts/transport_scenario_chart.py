# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Graphique de scénario pour le transport des consommables.

import numpy as np
import matplotlib
matplotlib.use('QtAgg')

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFileDialog, QToolBar, QStyle, QMessageBox
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, Signal
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from ui.charts.transport_utils import (
    COLOR_ERR,
    COLOR_TRANSPORT,
    add_transport_summary,
    apply_transport_tight_layout,
    iter_transport_records,
    origin_color,
    scenario_europe,
    set_vertical_text_room,
    summarize_transport,
)


class TransportScenarioChartWindow(QDialog):
    """Comparaison du transport actuel avec un scénario provenance Europe."""

    finished = Signal()

    def __init__(self, main_window):
        super().__init__(parent=main_window)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self.main_window = main_window
        self.setWindowTitle("Scénario transport Europe")
        self.setGeometry(300, 200, 980, 620)

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

        scenario = scenario_europe(records, self.main_window.data_manager)
        self._plot(scenario, summarize_transport(records))

    def _plot(self, scenario, summary):
        grid = self.figure.add_gridspec(1, 2, width_ratios=[1.0, 1.35])
        ax_compare = self.figure.add_subplot(grid[0, 0])
        ax_gain = self.figure.add_subplot(grid[0, 1])

        current_total = scenario["current_total"]
        scenario_total = scenario["scenario_total"]
        gain = scenario["gain"]
        compare_labels = ["Actuel", "Scénario\nEurope"]
        compare_values = [current_total, scenario_total]
        peak = set_vertical_text_room(ax_compare, compare_values, room_ratio=0.28)
        compare_colors = [COLOR_TRANSPORT, "#2563eb"]
        bars = ax_compare.bar(compare_labels, compare_values, color=compare_colors, edgecolor='white')

        for bar, value in zip(bars, compare_values):
            ax_compare.text(
                bar.get_x() + bar.get_width() / 2,
                value + peak * 0.03,
                f"{value:.1f} kg",
                ha='center',
                va='bottom',
                fontsize=8,
                color=COLOR_ERR,
                clip_on=True,
            )

        ax_compare.set_title("Transport actuel vs scénario", fontsize=11, pad=14)
        ax_compare.set_ylabel("Émissions transport (kg CO₂e)", fontsize=9)
        ax_compare.spines['top'].set_visible(False)
        ax_compare.spines['right'].set_visible(False)
        delta_label = "Économie" if gain >= 0 else "Hausse"
        ax_compare.text(
            0.5,
            0.88,
            f"{delta_label} : {abs(gain):.1f} kg CO₂e",
            transform=ax_compare.transAxes,
            ha='center',
            va='center',
            fontsize=9,
            color="#166534" if gain >= 0 else "#b91c1c",
            bbox={
                "boxstyle": "round,pad=0.3",
                "facecolor": "#f0fdf4" if gain >= 0 else "#fef2f2",
                "edgecolor": "#bbf7d0" if gain >= 0 else "#fecaca",
            },
        )

        gains = [
            (origin, value)
            for origin, value in scenario["gains_by_origin"].items()
            if abs(value) > 1e-9
        ]
        gains.sort(key=lambda item: item[1], reverse=True)

        if not gains:
            ax_gain.text(
                0.5, 0.5,
                "Aucun écart : les provenances sont déjà France/Europe.",
                ha='center', va='center', transform=ax_gain.transAxes
            )
            ax_gain.set_axis_off()
        else:
            origins = [origin for origin, _ in gains]
            values = np.array([value for _, value in gains])
            y = np.arange(len(gains))
            ax_gain.barh(
                y,
                values,
                color=[origin_color(origin) for origin in origins],
                edgecolor='white',
            )
            ax_gain.set_yticks(y)
            ax_gain.set_yticklabels(origins, fontsize=8)
            ax_gain.invert_yaxis()
            max_abs = max(float(np.abs(values).max()), 1.0)

            if np.all(values >= 0):
                ax_gain.set_xlim(0, max_abs * 1.45)
                ax_gain.set_xlabel("kg CO₂e évités en passant à Europe", fontsize=9)
            else:
                min_value = min(float(values.min()), 0.0)
                max_value = max(float(values.max()), 0.0)
                ax_gain.axvline(0, color='#94a3b8', linewidth=0.8)
                ax_gain.set_xlim(min_value * 1.45, max_value * 1.45)
                ax_gain.set_xlabel("kg CO₂e évités (négatif = hausse)", fontsize=9)

            for i, value in enumerate(values):
                x = value + (max_abs * 0.03 if value >= 0 else -max_abs * 0.03)
                ha = 'left' if value >= 0 else 'right'
                label = f"{abs(value):.1f} kg évités" if value >= 0 else f"{abs(value):.1f} kg en plus"
                ax_gain.text(
                    x, y[i], label,
                    va='center', ha=ha, fontsize=8,
                    color="#166534" if value >= 0 else "#b91c1c",
                    clip_on=True
                )

            ax_gain.set_title("Émissions évitées par provenance actuelle", fontsize=11, pad=14)
            ax_gain.spines['top'].set_visible(False)
            ax_gain.spines['right'].set_visible(False)

        add_transport_summary(self.figure, summary, gain=gain)
        apply_transport_tight_layout(self.figure, rect=(0, 0, 0.95, 0.86))
        self.canvas.draw()

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
                QMessageBox.warning(self, 'Erreur', f"Erreur lors de l'enregistrement : {e}")
        else:
            QMessageBox.information(self, 'Annulation', 'Enregistrement annulé.')

    def closeEvent(self, event):
        self.finished.emit()
        super().closeEvent(event)
