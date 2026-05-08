# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Graphique des principaux contributeurs transport.

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
    summarize_transport,
)


class TransportTopChartWindow(QDialog):
    """Top des lignes qui contribuent le plus aux émissions de transport."""

    finished = Signal()

    def __init__(self, main_window):
        super().__init__(parent=main_window)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self.main_window = main_window
        self.setWindowTitle("Top des émissions de transport")
        self.setGeometry(300, 200, 980, 640)

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

        records.sort(key=lambda record: record["transport_emissions"], reverse=True)
        self._plot(records[:10], summarize_transport(records), len(records))

    def _plot(self, records, summary, total_count):
        ax = self.figure.add_subplot(111)

        y = np.arange(len(records))
        values = np.array([record["transport_emissions"] for record in records])
        max_val = max(float(values.max()), 1.0)
        transport_total = max(summary["transport_total"], 1e-12)

        bars = ax.barh(
            y,
            values,
            color=[origin_color(record["origin"]) for record in records],
            edgecolor='white',
        )

        ax.set_yticks(y)
        ax.set_yticklabels([record["label"] for record in records], fontsize=8)
        ax.invert_yaxis()

        for bar, record, value in zip(bars, records, values):
            pct = value / transport_total * 100.0
            ax.text(
                value + max_val * 0.012,
                bar.get_y() + bar.get_height() / 2,
                f"{value:.1f} kg ({pct:.0f} %)",
                va='center',
                ha='left',
                fontsize=7,
                color=COLOR_ERR,
                clip_on=True,
            )

        title = "Top transport des consommables"
        if total_count > len(records):
            title += f" - top {len(records)} / {total_count}"
        ax.set_title(title, fontsize=11, pad=14)
        ax.set_xlabel("Émissions transport (kg CO₂e)", fontsize=9)
        ax.set_xlim(0, max_val * 1.45)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        origins = []
        for record in records:
            if record["origin"] not in origins:
                origins.append(record["origin"])
        legend_elements = [
            Patch(facecolor=origin_color(origin), label=origin)
            for origin in origins
        ]
        ax.legend(
            handles=legend_elements,
            title="Provenance",
            fontsize=8,
            title_fontsize=8,
            framealpha=0.9,
            edgecolor='#cbd5e1',
            loc='center right',
            bbox_to_anchor=(0.985, 0.46),
            bbox_transform=self.figure.transFigure,
        )

        add_transport_summary(self.figure, summary)
        apply_transport_tight_layout(self.figure, rect=(0, 0, 0.72, 0.86))
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
