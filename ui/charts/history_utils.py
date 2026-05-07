# SPDX-License-Identifier: GPL-3.0-or-later
"""Accès commun aux données stockées dans l'historique."""

from PySide6.QtCore import Qt


def iter_history_data(history_widget):
    """
    Itère sur les dicts de calcul stockés dans l'historique.

    L'application utilise maintenant un QTableWidget, avec les données complètes
    rangées dans la colonne 0. Le fallback conserve la compatibilité avec
    l'ancien QListWidget.
    """
    if history_widget is None:
        return

    if hasattr(history_widget, "rowCount"):
        for row in range(history_widget.rowCount()):
            item = history_widget.item(row, 0)
            if item is not None:
                data = item.data(Qt.UserRole)
                if data:
                    yield data
        return

    if hasattr(history_widget, "count"):
        for index in range(history_widget.count()):
            item = history_widget.item(index)
            if item is not None:
                data = item.data(Qt.UserRole)
                if data:
                    yield data
