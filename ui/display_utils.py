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


def looks_like_liquid_commercial_product(
    row,
    *,
    factor_col="Facteur liquide source",
    unit_col="Unité liquide",
    volume_col="Volume flacon (mL)",
    name_col="Consommable",
    code_col="Code NACRES",
):
    """
    Distingue un vrai produit liquide d'un objet solide qui a seulement une capacité.

    Dans la base actuelle, "Unité liquide" et "Volume flacon (mL)" peuvent aussi
    représenter la capacité d'une boîte, d'un sac, d'une étiquette pour tube, etc.
    Ces champs ne suffisent donc pas à classifier la ligne comme liquide.
    """
    if row is None:
        return False

    factor_name = clean_text(row.get(factor_col, ""))
    if factor_name:
        return True

    unit = clean_text(row.get(unit_col, ""))
    volume = safe_float(row.get(volume_col, 0.0), default=0.0)
    if not unit and volume <= 0:
        return False

    name = normalize_search(row.get(name_col, ""))
    code = normalize_nacres_prefix(row.get(code_col, ""))
    if not name and not code:
        return False

    solid_capacity_terms = (
        "boite", "box", "sac", "bag", "etiquette", "label",
        "tube", "microtube", "pipette", "flacon vide", "bouteille vide",
        "bidon vide", "reservoir", "poubelle", "dechet", "aiguille", "lame",
        "cryo-tag", "cryotag", "touch-spots",
    )
    if any(term in name for term in solid_capacity_terms):
        return False

    if code.startswith("NA"):
        return True

    liquid_terms = (
        "solution", "soln", "liquide", "liquid", "solvant", "solvent",
        "milieu", "medium", "buffer", "tampon", "acide", "acid",
        "ethanol", "methanol", "propanol", "isopropanol", "acetone",
        "acetonitrile", "chloroforme", "formamide", "dmso", "glycerol",
        "glycogen", "temed", "sds", "tae", "tbe", "tris-glycine",
        "bromide", "sybr", "stain", "hydroxyde", "hydroxide",
    )
    return any(term in name for term in liquid_terms)


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
