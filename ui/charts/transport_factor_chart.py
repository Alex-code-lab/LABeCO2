# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# ui/charts/transport_factor_chart.py

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

from ui.charts.history_utils import iter_history_data

_COLOR_BAR = '#f59e0b'   # ambre : transport
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

        trans_by_origin = {}   # kg CO₂e transport uniquement
        total_by_origin = {}   # kg CO₂e émissions masse totales (pour le %)
        err_by_origin   = {}   # variance cumulée

        for data in iter_history_data(self.main_window.history_list):
            em  = float(data.get('emission_mass', 0.0) or 0.0)
            tm  = float(data.get('total_mass',    0.0) or 0.0)
            err = float(data.get('emission_mass_error', 0.0) or 0.0)

            if em <= 0 or tm <= 0:
                continue

            origine = data.get('origine', dm.TRANSPORT_DEFAULT) or dm.TRANSPORT_DEFAULT
            transport_factor, transport_uncert = dm.get_transport_factor(origine)

            trans_em  = tm * transport_factor
            trans_err = trans_em * transport_uncert

            if origine not in trans_by_origin:
                trans_by_origin[origine] = 0.0
                total_by_origin[origine] = 0.0
                err_by_origin[origine]   = 0.0

            trans_by_origin[origine] += trans_em
            total_by_origin[origine] += em
            err_by_origin[origine]   += trans_err ** 2

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
        self._plot(origins, trans_by_origin, total_by_origin, err_by_origin, dm)

    # ------------------------------------------------------------------
    def _plot(self, origins, trans_dict, total_dict, err_dict, dm):
        n = len(origins)
        x = np.arange(n)
        bar_w = 0.55

        trans_vals = np.array([trans_dict[o] for o in origins])
        total_vals = np.array([total_dict[o] for o in origins])
        errs       = np.array([err_dict[o]   for o in origins])
        pct_vals   = np.where(total_vals > 0, trans_vals / total_vals * 100, 0.0)

        ax = self.figure.add_subplot(111)

        bars = ax.bar(x, trans_vals, bar_w,
                      color=_COLOR_BAR, edgecolor='white')

        ax.errorbar(x, trans_vals, yerr=errs,
                    fmt='none', ecolor='#374151', capsize=5, capthick=1, lw=0.8, zorder=5)

        # Facteur de transport et pourcentage au-dessus de chaque barre
        max_val = trans_vals.max() if trans_vals.max() > 0 else 1.0
        for i, (orig, tv, pct, err) in enumerate(zip(origins, trans_vals, pct_vals, errs)):
            factor, _ = dm.get_transport_factor(orig)
            label = f"{pct:.0f}% du total masse\n({factor:.3f} kg CO₂e/kg)"
            ax.text(x[i], tv + err + max_val * 0.015,
                    label, ha='center', va='bottom', fontsize=7, color=_COLOR_PCT)

        # Valeur numérique à l'intérieur des barres (si assez hautes)
        for i, tv in enumerate(trans_vals):
            if tv > max_val * 0.08:
                ax.text(x[i], tv / 2, f"{tv:.1f}",
                        ha='center', va='center', fontsize=8,
                        color='white', fontweight='bold')

        short_origins = [o.replace(' (', '\n(') for o in origins]
        ax.set_xticks(x)
        ax.set_xticklabels(short_origins, fontsize=8)

        ax.set_ylabel("Émissions transport (kg CO₂e)", fontsize=9)
        ax.set_title(
            "Émissions dues au transport par provenance",
            fontsize=11
        )
        ax.set_xlim(-0.5, n - 0.5)

        # Marge verticale pour les annotations
        ax.set_ylim(0, max_val * 1.35)

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
