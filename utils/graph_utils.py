# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# utils/graph_utils.py

import matplotlib.pyplot as plt

def plot_pie_chart(ax, labels, values, colors, title):
    """
    Crée un diagramme en secteurs.

    Paramètres :
    ------------
    ax : matplotlib.axes.Axes
        Axe sur lequel tracer le graphique.
    labels : list
        Liste des étiquettes.
    values : list
        Liste des valeurs associées.
    colors : list
        Liste des couleurs à utiliser.
    title : str
        Titre du graphique.
    """
    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        colors=colors,
        autopct='%1.1f%%',
        startangle=90,
        textprops={'color': 'black'}
    )
    ax.set_title(title)
    ax.axis('equal')  # Pour garantir un cercle parfait