"""
merge_prix_consommables.py

Produit un catalogue complet en gardant les lignes saisies a la main separees
des lignes prix issues du catalogue IJM.

Usage :
    python Scrapping/merge_prix_consommables.py

Entrées :
    Scrapping/masses_consommable - liste consommables (1).csv
    Scrapping/output/prix_ijm_2025.csv

Sorties :
    Scrapping/output/masses_consommable_with_prix.csv
        → Consommables de la base masse, sans prix catalogue injecte
          automatiquement.

    Scrapping/output/catalogue_complet.csv
        → Base masse + produits IJM en lignes separees. Le prix catalogue est
          stocke dans "Prix du conditionnement"; la provenance dans
          "Source catalogue IJM".
"""

import os
import csv
import re
from datetime import date
from difflib import SequenceMatcher

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MASSES_CSV = os.path.join(BASE_DIR, "masses_consommable - liste consommables (1).csv")
PRIX_CSV   = os.path.join(BASE_DIR, "output", "prix_ijm_2025.csv")
OUT_MASSE  = os.path.join(BASE_DIR, "output", "masses_consommable_with_prix.csv")
OUT_COMPLET= os.path.join(BASE_DIR, "output", "catalogue_complet.csv")
RUN_DATE = date.today().isoformat()

os.makedirs(os.path.join(BASE_DIR, "output"), exist_ok=True)

# ── Familles de produits (mots-clés en / fr) ─────────────────────────────────
# Si BASE et IJM partagent une famille → match "même famille" → on garde.
FAMILIES = [
    {"tube", "tubes", "centrifug", "microtu", "fliptube", "cryotube"},
    {"seringue", "seringues", "syringe", "syringes"},
    {"pipette", "pipettes", "serolog"},
    {"pointe", "pointes", "tip", "tips", "cone", "cones"},
    {"gant", "gants", "glove", "gloves", "nitrile", "latex", "kevlar"},
    {"boite", "dish", "petri", "pétri"},
    {"flask", "flacon", "flacons"},
    {"plaque", "plate", "puits", "well", "wells"},
    {"pissette", "dropper"},
    {"filtre", "filter", "filters"},
    {"grattoir", "scraper", "cell scraper"},
    {"aiguille", "needle", "needles"},
]


def tokens(text):
    """Retourne un ensemble de sous-chaînes minuscules (mots partiels)."""
    text = text.lower()
    return set(text.split())


def same_family(name_a, name_b):
    """
    Retourne True si les deux noms appartiennent à la même famille de produit.
    Comparaison par sous-chaîne : un mot-clé de la famille doit être contenu
    dans chacun des deux noms.
    """
    a = name_a.lower()
    b = name_b.lower()
    for family in FAMILIES:
        in_a = any(kw in a for kw in family)
        in_b = any(kw in b for kw in family)
        if in_a and in_b:
            return True
    return False


def load_csv(path, encoding="utf-8-sig"):
    with open(path, newline="", encoding=encoding) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = reader.fieldnames or []
    return rows, fields


def extract_code4(code_nacres_long):
    return code_nacres_long.strip()[:4].upper()


def build_prix_index(prix_rows):
    index = {}
    for row in prix_rows:
        code4 = row["code_nacres"].strip()[:4].upper()
        index.setdefault(code4, []).append(row)
    return index


def packaging_text(row):
    return f"{row.get('condt', '')} {row.get('designation', '')}".casefold().replace(",", ".")


def infer_unit(row):
    text = packaging_text(row)
    if re.search(r"\d+(?:\.\d+)?\s*(?:µl|μl|ul|ml|millilitres?|milliliters?)\b", text):
        return "mL"
    if re.search(r"\d+(?:\.\d+)?\s*(?:l|litres?|liters?)\b", text):
        return "mL"
    if re.search(r"\d+(?:\.\d+)?\s*kg\b", text) or re.search(r"\d+(?:\.\d+)?\s*g\b", text):
        return "g"
    return ""


def is_liquid_catalogue_row(row):
    return row["code_nacres"].strip()[:4].upper().startswith("NA") and infer_unit(row) == "mL"


def infer_conditionnement_mass_g(row):
    text = packaging_text(row)
    match_kg = re.search(r"(\d+(?:\.\d+)?)\s*kg\b", text)
    if match_kg:
        return str(float(match_kg.group(1)) * 1000.0)
    match_g = re.search(r"(\d+(?:\.\d+)?)\s*g\b", text)
    if match_g:
        return str(float(match_g.group(1)))
    return ""


def clean(value):
    text = str(value or "").strip()
    return "" if text.lower() in {"", "nan", "none", "n/a"} else text


def looks_like_documentary_source(value):
    text = clean(value)
    return bool(
        text and re.search(r"https?://|www\.|doi\s*:|doi\.org|10\.\d{4,9}/", text, flags=re.IGNORECASE)
    )


def normalize_source_signature_fields(row):
    """Ancienne base consommables: Source/Signature correspond à la signature."""
    out = {k: v for k, v in row.items() if k != "Source/Signature"}
    out.setdefault("Source", "")
    out.setdefault("Signature", "")
    if not clean(out.get("Signature")):
        out["Signature"] = clean(row.get("Signature")) or clean(row.get("Source/Signature"))
    if not clean(out.get("Source")) and looks_like_documentary_source(row.get("Lien / Note / Remarque")):
        out["Source"] = clean(row.get("Lien / Note / Remarque"))
    return out


def best_match(consommable_name, candidates):
    """
    Parmi les candidats, cherche d'abord dans la même famille produit.
    Si des candidats de même famille existent, prend le meilleur score parmi eux.
    Sinon, prend le meilleur score global (sera ensuite rejeté par l'appelant).
    """
    name_lower = consommable_name.lower()

    same_fam = [r for r in candidates if same_family(consommable_name, r["designation"])]
    pool = same_fam if same_fam else candidates

    best_score = -1.0
    best_row = pool[0]
    for row in pool:
        score = SequenceMatcher(None, name_lower, row["designation"].lower()).ratio()
        if score > best_score:
            best_score = score
            best_row = row
    return best_row, round(best_score, 3), bool(same_fam)


# ── Colonnes ajoutées côté catalogue ──────────────────────────────────────────
PRIX_FIELDS = [
    "code_nacres_court",
    "Source catalogue IJM",
    "condt_ijm",
    "designation_ijm",
    "code_ijm",
    "marque_ijm",
    "score_match",
]


def merge():
    masses_rows, masses_fields = load_csv(MASSES_CSV)
    prix_rows, _               = load_csv(PRIX_CSV)

    out_fields = []
    for field in masses_fields:
        if field == "Source/Signature":
            if "Source" not in out_fields:
                out_fields.append("Source")
            if "Signature" not in out_fields:
                out_fields.append("Signature")
        elif field not in out_fields:
            out_fields.append(field)
    for col in ["Prix du conditionnement", "Nbr par conditionnement"]:
        if col not in out_fields:
            out_fields.append(col)
    for col in ["Unité liquide", "Volume flacon (mL)", "Facteur liquide source", "date d'ajout"]:
        if col not in out_fields:
            out_fields.append(col)
    for col in PRIX_FIELDS:
        if col not in out_fields:
            out_fields.append(col)

    results = []

    for row in masses_rows:
        row = normalize_source_signature_fields(row)
        code_long   = row.get("Code NACRES", "").strip()
        code4       = extract_code4(code_long)

        extra = {f: "" for f in PRIX_FIELDS}
        extra["code_nacres_court"] = code4

        results.append({**row, **extra})

    # ── Fichier 1 : masses enrichies ─────────────────────────────────────────
    with open(OUT_MASSE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(results)

    # ── Fichier 2 : catalogue complet ────────────────────────────────────────
    # Lignes IJM en lignes separees -> colonnes masse vides.
    # Les codes NA* volumiques restent dans les consommables comme produits
    # commerciaux; le facteur est reference depuis la base Liquides & Solvants.
    ijm_only_rows = []
    seen_ijm_codes = set()
    for row in prix_rows:
        code_ijm = row.get("code_ijm", "").strip()
        if code_ijm and code_ijm in seen_ijm_codes:
            continue
        if code_ijm:
            seen_ijm_codes.add(code_ijm)
        code4 = row["code_nacres"].strip()[:4].upper()
        masse_empty = {f: "" for f in out_fields}
        page = row.get("page", "").strip()
        prix_extra  = {
            "code_nacres_court": code4,
            "Source catalogue IJM": f"Catalogue IJM 2025, page {page}" if page else "Catalogue IJM 2025",
            "condt_ijm"        : row["condt"],
            "designation_ijm"  : row["designation"],
            "code_ijm"         : row["code_ijm"],
            "marque_ijm"       : row["marque"],
            "score_match"      : "",
        }
        # On peut pré-remplir quelques champs évidents
        masse_empty["Consommable"] = row["designation"]
        masse_empty["Marque"]      = row["marque"]
        masse_empty["Référence"]   = row["code_ijm"]
        masse_empty["Catégorie"]   = "Autres consommables"
        masse_empty["Code NACRES"] = row["code_nacres"]
        masse_empty["Masse unitaire (g)"] = infer_conditionnement_mass_g(row)
        masse_empty["Prix du conditionnement"] = row["prix_ht"]
        masse_empty["Nbr par conditionnement"] = row["nb_unites"]
        if is_liquid_catalogue_row(row):
            masse_empty["Unité liquide"] = "mL"
            # La base facteur est choisie/enrichie dans migrate_ijm_price_schema.py.
            masse_empty["Facteur liquide source"] = ""
            # Fonction volontairement simple ici: le script de migration reste
            # la référence pour l'inférence précise.
            text = packaging_text(row)
            vol = ""
            match_ml = re.search(r"(\d+(?:\.\d+)?)\s*(?:ml|millilitres?|milliliters?)\b", text)
            match_l = re.search(r"(\d+(?:\.\d+)?)\s*(?:l|litres?|liters?)\b", text)
            if match_ml:
                vol = match_ml.group(1)
            elif match_l:
                vol = str(float(match_l.group(1)) * 1000.0)
            masse_empty["Volume flacon (mL)"] = vol
        masse_empty["date d'ajout"] = RUN_DATE

        ijm_only_rows.append({**masse_empty, **prix_extra})

    complet_rows = results + ijm_only_rows

    with open(OUT_COMPLET, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(complet_rows)

    # ── Résumé ────────────────────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print(f"Consommables traités        : {len(masses_rows)}")
    print("  Prix IJM injectés         : 0 (lignes catalogue séparées)")
    print(f"\nFichier 1 ({len(results)} lignes)      : {OUT_MASSE}")
    print(f"Fichier 2 ({len(complet_rows)} lignes) : {OUT_COMPLET}")
    print(f"  dont {len(ijm_only_rows)} produits IJM sans données masse (à compléter)")
    print(f"{'─'*70}\n")

    print(f"  Produits IJM séparés      : {len(ijm_only_rows)}")


if __name__ == "__main__":
    merge()
