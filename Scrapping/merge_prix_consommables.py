"""
merge_prix_consommables.py

Enrichit le fichier de masses des consommables avec les prix du catalogue IJM,
puis produit un catalogue complet en ajoutant les produits IJM non matchés.

Usage :
    python Scrapping/merge_prix_consommables.py

Entrées :
    Scrapping/masses_consommable - liste consommables (1).csv
    Scrapping/output/prix_ijm_2025.csv

Sorties :
    Scrapping/output/masses_consommable_with_prix.csv
        → Consommables de la base masse enrichis des prix IJM.
          Seuls les matchs "même famille produit" sont conservés.

    Scrapping/output/catalogue_complet.csv
        → Tout : base masse (enrichie) + produits IJM sans correspondance masse.
          Les colonnes masse sont vides pour les produits IJM seuls.
"""

import os
import csv
from difflib import SequenceMatcher

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MASSES_CSV = os.path.join(BASE_DIR, "masses_consommable - liste consommables (1).csv")
PRIX_CSV   = os.path.join(BASE_DIR, "output", "prix_ijm_2025.csv")
OUT_MASSE  = os.path.join(BASE_DIR, "output", "masses_consommable_with_prix.csv")
OUT_COMPLET= os.path.join(BASE_DIR, "output", "catalogue_complet.csv")

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


# ── Colonnes ajoutées côté prix ───────────────────────────────────────────────
PRIX_FIELDS = [
    "code_nacres_court",
    "prix_ht_ijm",
    "condt_ijm",
    "nb_unites_ijm",
    "prix_unitaire_ijm",
    "designation_ijm",
    "code_ijm",
    "marque_ijm",
    "score_match",
]


def merge():
    masses_rows, masses_fields = load_csv(MASSES_CSV)
    prix_rows, _               = load_csv(PRIX_CSV)

    prix_index = build_prix_index(prix_rows)

    out_fields = list(masses_fields) + PRIX_FIELDS

    results     = []       # lignes enrichies pour fichier 1
    matched_ijm = set()    # index des lignes IJM utilisées (pour fichier 2)

    kept = 0
    removed = 0

    for row in masses_rows:
        code_long   = row.get("Code NACRES", "").strip()
        consommable = row.get("Consommable", "").strip()
        code4       = extract_code4(code_long)

        extra = {f: "" for f in PRIX_FIELDS}
        extra["code_nacres_court"] = code4

        candidates = prix_index.get(code4)
        if candidates:
            best, score, has_family = best_match(consommable, candidates)
            if has_family:
                extra["prix_ht_ijm"]       = best["prix_ht"]
                extra["condt_ijm"]         = best["condt"]
                extra["nb_unites_ijm"]     = best["nb_unites"]
                extra["prix_unitaire_ijm"] = best["prix_unitaire"]
                extra["designation_ijm"]   = best["designation"]
                extra["code_ijm"]          = best["code_ijm"]
                extra["marque_ijm"]        = best["marque"]
                extra["score_match"]       = score
                matched_ijm.add(best["code_ijm"])
                kept += 1
            else:
                extra["score_match"] = f"REMOVED({score})"
                removed += 1

        results.append({**row, **extra})

    # ── Fichier 1 : masses enrichies ─────────────────────────────────────────
    with open(OUT_MASSE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(results)

    # ── Fichier 2 : catalogue complet ────────────────────────────────────────
    # Lignes IJM non utilisées → colonnes masse vides
    ijm_only_rows = []
    for row in prix_rows:
        if row["code_ijm"] in matched_ijm:
            continue  # déjà représentée côté masse

        masse_empty = {f: "" for f in masses_fields}
        prix_extra  = {
            "code_nacres_court": row["code_nacres"].strip()[:4].upper(),
            "prix_ht_ijm"      : row["prix_ht"],
            "condt_ijm"        : row["condt"],
            "nb_unites_ijm"    : row["nb_unites"],
            "prix_unitaire_ijm": row["prix_unitaire"],
            "designation_ijm"  : row["designation"],
            "code_ijm"         : row["code_ijm"],
            "marque_ijm"       : row["marque"],
            "score_match"      : "",
        }
        # On peut pré-remplir quelques champs évidents
        masse_empty["Consommable"] = row["designation"]
        masse_empty["Marque"]      = row["marque"]
        masse_empty["Code NACRES"] = row["code_nacres"]

        ijm_only_rows.append({**masse_empty, **prix_extra})

    complet_rows = results + ijm_only_rows

    with open(OUT_COMPLET, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(complet_rows)

    # ── Résumé ────────────────────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print(f"Consommables traités        : {len(masses_rows)}")
    print(f"  Matchés (même famille)    : {kept}")
    print(f"  Supprimés (famille diff.) : {removed}")
    print(f"\nFichier 1 ({len(results)} lignes)      : {OUT_MASSE}")
    print(f"Fichier 2 ({len(complet_rows)} lignes) : {OUT_COMPLET}")
    print(f"  dont {len(ijm_only_rows)} produits IJM sans données masse (à compléter)")
    print(f"{'─'*70}\n")

    print(f"{'Score':<14} {'Consommable (base)':<33} {'Désignation IJM':<38} Code")
    print("-" * 95)
    for r in sorted(results, key=lambda x: str(x["score_match"])):
        score = r["score_match"]
        flag  = " ✗" if str(score).startswith("REMOVED") else ""
        print(
            f"{str(score):<14} "
            f"{r['Consommable'][:31]:<33} "
            f"{r.get('designation_ijm','')[:36]:<38} "
            f"{r['code_nacres_court']}{flag}"
        )


if __name__ == "__main__":
    merge()
