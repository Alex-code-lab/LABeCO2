# SPDX-License-Identifier: GPL-3.0-or-later
"""Helpers d'affichage UI indépendants des libellés exacts de la base."""

import unicodedata


def normalize_search(text):
    """Casefold + suppression des accents pour une recherche insensible aux diacritiques."""
    return unicodedata.normalize('NFD', str(text).casefold()).encode('ascii', 'ignore').decode('ascii')


def clean_text(value):
    """Retourne une chaîne propre pour une valeur potentiellement vide/NaN."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.casefold() in {"nan", "none", "nat"}:
        return ""
    return text


def safe_float(value, default=0.0):
    """Convertit une cellule numérique avec tolérance aux virgules et NaN."""
    text = clean_text(value).replace(",", ".")
    if not text:
        return default
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def format_quantity(value):
    """Formate une quantité sans décimales inutiles."""
    number = safe_float(value, default=0.0)
    if number.is_integer():
        return str(int(number))
    return f"{number:.4f}".rstrip("0").rstrip(".")


def normalize_nacres_prefix(value):
    """Retourne le préfixe NACRES de comparaison, en général les 4 premiers caractères."""
    return clean_text(value).upper()[:4]


def is_consumables_subcategory(value):
    return clean_text(value).casefold().startswith("consommable")


def format_subcategory_label(value):
    """
    Renvoie (texte_affiche, tooltip) pour une sous-catégorie.

    Exemple :
    "Consommables (Matières premières...)" -> ("Consommables", "Matières premières...")
    """
    text = clean_text(value)
    if not is_consumables_subcategory(text):
        return text, ""

    start = text.find("(")
    end = text.rfind(")")
    tooltip = ""
    if start != -1 and end > start:
        tooltip = text[start + 1:end].strip()

    return "Consommables", tooltip


def display_unit(unit):
    unit_text = clean_text(unit)
    if unit_text.casefold() == "euro":
        return "€"
    return unit_text
