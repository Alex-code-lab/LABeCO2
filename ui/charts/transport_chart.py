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

from ui.charts.history_utils import iter_history_data

_COLOR_MATERIAL  = '#73c2fb'   # bleu : émissions matière
_COLOR_TRANSPORT = '#f59e0b'   # ambre : émissions transport
_COLOR_ERR       = '#374151'   # gris foncé pour les barres d'erreur


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

        dm = self.main_window.data_manager

        # Accumulation par provenance
        # Pour chaque item avec masse : recalcule la part transport
        mat_by_origin   = {}   # émissions matière (kg CO₂e)
        trans_by_origin = {}   # émissions transport (kg CO₂e)
        err_by_origin   = {}   # variance cumulée pour les barres d'erreur

        for data in iter_history_data(self.main_window.history_list):
            em    = float(data.get('emission_mass', 0.0) or 0.0)
            tm    = float(data.get('total_mass',    0.0) or 0.0)
            em_err = float(data.get('emission_mass_error', 0.0) or 0.0)

            if em <= 0 or tm <= 0:
                continue  # pas de calcul masse pour cet item

            origine = data.get('origine', dm.TRANSPORT_DEFAULT) or dm.TRANSPORT_DEFAULT
            transport_factor, transport_uncert = dm.get_transport_factor(origine)

            trans_em  = tm * transport_factor
            trans_err = trans_em * transport_uncert
            mat_em    = max(em - trans_em, 0.0)
            mat_err   = max(em_err - trans_err, 0.0)  # approximation conservative

            if origine not in mat_by_origin:
                mat_by_origin[origine]   = 0.0
                trans_by_origin[origine] = 0.0
                err_by_origin[origine]   = 0.0

            mat_by_origin[origine]   += mat_em
            trans_by_origin[origine] += trans_em
            err_by_origin[origine]   += (em_err ** 2)

        if not mat_by_origin:
            ax = self.figure.add_subplot(111)
            ax.text(
                0.5, 0.5,
                "Aucune donnée de masse disponible dans l'historique.",
                ha='center', va='center', transform=ax.transAxes
            )
            self.canvas.draw()
            return

        # Convertir variances en écarts-types
        for k in err_by_origin:
            err_by_origin[k] = err_by_origin[k] ** 0.5

        # Trier par émissions totales décroissantes
        origins = sorted(
            mat_by_origin.keys(),
            key=lambda o: mat_by_origin[o] + trans_by_origin[o],
            reverse=True
        )

        self._plot(origins, mat_by_origin, trans_by_origin, err_by_origin)

    # ------------------------------------------------------------------
    def _plot(self, origins, mat_dict, trans_dict, err_dict):
        n = len(origins)
        x = np.arange(n)
        bar_w = 0.55

        mat_vals   = np.array([mat_dict[o]   for o in origins])
        trans_vals = np.array([trans_dict[o] for o in origins])
        totals     = mat_vals + trans_vals
        errs       = np.array([err_dict[o]   for o in origins])

        ax = self.figure.add_subplot(111)

        bars_mat   = ax.bar(x, mat_vals,   bar_w,
                            color=_COLOR_MATERIAL,  edgecolor='white', label='Matière')
        bars_trans = ax.bar(x, trans_vals, bar_w,
                            bottom=mat_vals,
                            color=_COLOR_TRANSPORT, edgecolor='white', label='Transport')

        # Barres d'erreur sur le total
        ax.errorbar(x, totals, yerr=errs,
                    fmt='none', ecolor=_COLOR_ERR, capsize=5, capthick=1, lw=0.8, zorder=5)

        # Pourcentage transport au-dessus de chaque barre
        for i, (tot, tr) in enumerate(zip(totals, trans_vals)):
            if tot > 0:
                pct = tr / tot * 100
                ax.text(x[i], tot + errs[i] + tot * 0.015,
                        f"{pct:.0f}%\ntransport",
                        ha='center', va='bottom', fontsize=7, color=_COLOR_ERR)

        # Valeurs numériques à l'intérieur des barres (si assez hautes)
        for i, (mv, tv) in enumerate(zip(mat_vals, trans_vals)):
            if mv > totals.max() * 0.06:
                ax.text(x[i], mv / 2,
                        f"{mv:.1f}", ha='center', va='center', fontsize=7, color='white')
            if tv > totals.max() * 0.06:
                ax.text(x[i], mv + tv / 2,
                        f"{tv:.1f}", ha='center', va='center', fontsize=7, color='white')

        # Étiquettes axe X : nom provenance sur deux lignes si nécessaire
        short_origins = [o.replace(' (', '\n(') for o in origins]
        ax.set_xticks(x)
        ax.set_xticklabels(short_origins, fontsize=8)

        ax.set_ylabel("Émissions (kg CO₂e)", fontsize=9)
        ax.set_title(
            "Émissions par provenance : part matière et part transport",
            fontsize=11
        )
        ax.set_xlim(-0.5, n - 0.5)

        legend_elements = [
            Patch(facecolor=_COLOR_MATERIAL,  label='Émissions matière'),
            Patch(facecolor=_COLOR_TRANSPORT, label='Émissions transport'),
        ]
        ax.legend(handles=legend_elements, fontsize=8,
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
