"""
parse_catalogue_ijm.py
Extrait les produits du catalogue PDF IJM et génère un CSV avec le prix unitaire.

Usage :
    python Scrapping/parse_catalogue_ijm.py

Sortie :
    Scrapping/output/prix_ijm_2025.csv

Colonnes CSV :
    code_nacres     - Code NACRES (= colonne "Code NOM" du catalogue, ex. HA01, NA21)
    designation     - Nom du produit (nettoyé)
    code_ijm        - Référence interne IJM (ex. E0342D)
    prix_ht         - Prix HT par conditionnement (€)
    condt           - Conditionnement brut (ex. "1 x200")
    nb_unites       - Nombre d'unités dans le conditionnement
    prix_unitaire   - Prix HT par unité (prix_ht / nb_unites)
    marque          - Marque / fournisseur
"""

import os
import re
import csv
from datetime import date
import pdfplumber

# ── Chemins ──────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
PDF_PATH   = os.path.join(BASE_DIR, "Catalogue IJM 2025.pdf")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
CSV_PATH   = os.path.join(OUTPUT_DIR, "prix_ijm_2025.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Nettoyage du texte ────────────────────────────────────────────────────────
_NOISE = re.compile(r'\bSur\s+Cde\b|\bNouveau\b|\bSupprimé\b.*', re.IGNORECASE)

def clean_text(s):
    """Supprime les annotations parasites (Sur Cde, Nouveau, Supprimé...)."""
    if not s:
        return ""
    return _NOISE.sub("", s).strip(" -")

# ── Parsing du conditionnement ────────────────────────────────────────────────
_CONDT_RE = re.compile(
    r'(\d+)\s*[xX×]\s*(\d+)',   # ex. 1x100, 10x96, 1 x 500
)

def parse_nb_unites(condt_str):
    """
    Retourne le nombre d'unités individuelles contenu dans un conditionnement.
    Exemples :
        "1 x100"  → 100
        "10x96"   → 960
        "1x25Kg"  → 1   (unité de masse, on garde 1)
        "1"       → 1
        "1x50"    → 50
    Retourne None si le conditionnement est ambigu (poids, volume en vrac...).
    """
    if not condt_str:
        return 1
    s = condt_str.strip()

    # Cas avec unité non-numérique après le chiffre (Kg, L, ml...) → 1 unité
    if re.search(r'\d\s*[xX×]\s*\d+\s*[A-Za-z]', s):
        return 1

    m = _CONDT_RE.search(s)
    if m:
        return int(m.group(1)) * int(m.group(2))

    # Juste un nombre
    m2 = re.match(r'^(\d+)$', s.strip())
    if m2:
        return int(m2.group(1))

    return 1

# ── Validation d'un Code IJM (référence alphanumérique) ──────────────────────
_CODE_IJM_RE = re.compile(r'^[A-Za-z]{1,5}\d{2,6}[A-Za-z0-9]*$')

def looks_like_code_ijm(s):
    return bool(s and _CODE_IJM_RE.match(s.strip()))

# ── Validation d'un Code NOM / NACRES (2 lettres + 2 chiffres) ───────────────
_CODE_NOM_RE = re.compile(r'^[A-Z]{2}\d{2,3}$')

def looks_like_code_nom(s):
    return bool(s and _CODE_NOM_RE.match(s.strip()))

# ── Validation d'un prix ──────────────────────────────────────────────────────
_PRIX_RE = re.compile(r'^\d{1,6}[,\.]\d{2}$')

def parse_prix(s):
    """Retourne float ou None."""
    if not s:
        return None
    s = s.strip().replace(',', '.')
    try:
        v = float(s)
        return v if v > 0 else None
    except ValueError:
        return None

# ── Extraction principale ─────────────────────────────────────────────────────
def extract_rows(pdf_path):
    """
    Parcourt toutes les pages du PDF et retourne une liste de dicts.
    Chaque dict représente une ligne produit valide.
    """
    rows = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):

            # pdfplumber détecte les tableaux automatiquement
            tables = page.extract_tables()

            for table in tables:
                for raw_row in table:
                    if raw_row is None:
                        continue

                    # Nettoyer les cellules None
                    cells = [c.strip() if c else "" for c in raw_row]

                    # Ignorer les lignes trop courtes
                    if len(cells) < 4:
                        continue

                    # ── Essayer d'identifier les colonnes ──────────────────
                    # Structure attendue du PDF :
                    #   [col0=vide/catégorie] [col1=vide/sous-cat] [DESIGNATION]
                    #   [Code IJM] [Prix HT] [Condt] [Code NOM] [Marque/Fourn]
                    #
                    # pdfplumber peut renvoyer des colonnes fusionnées différemment
                    # selon les pages. On identifie les colonnes par leur contenu.

                    designation = ""
                    code_ijm    = ""
                    prix_str    = ""
                    condt_str   = ""
                    code_nom    = ""
                    marque      = ""

                    # Chercher le Code IJM (alphanumérique court) et Prix HT
                    # dans toutes les cellules
                    for i, cell in enumerate(cells):
                        cell_clean = cell.strip()

                        if looks_like_code_ijm(cell_clean) and not code_ijm:
                            code_ijm = cell_clean
                            # La cellule juste avant est la désignation
                            if i > 0 and cells[i-1]:
                                designation = clean_text(cells[i-1])

                        elif looks_like_code_nom(cell_clean) and not code_nom:
                            code_nom = cell_clean
                            # La cellule suivante est la marque
                            if i + 1 < len(cells):
                                marque = clean_text(cells[i+1])

                        elif _PRIX_RE.match(cell_clean) and not prix_str:
                            prix_str = cell_clean
                            # La cellule suivante est le conditionnement
                            if i + 1 < len(cells):
                                condt_str = cells[i+1]

                    # Si la désignation est vide, essayer la première cellule non vide
                    if not designation:
                        for cell in cells:
                            c = clean_text(cell)
                            if c and not looks_like_code_ijm(c) and not looks_like_code_nom(c) and not _PRIX_RE.match(c):
                                designation = c
                                break

                    # Ignorer si pas de prix ou pas de code NOM
                    prix = parse_prix(prix_str)
                    if prix is None or not code_nom:
                        continue

                    # Ignorer les lignes sans désignation réelle
                    if not designation or len(designation) < 3:
                        continue

                    # Ignorer les en-têtes
                    if designation.upper() in ("DESIGNATION", "CODE IJM", "PRIX HT"):
                        continue

                    nb_unites    = parse_nb_unites(condt_str)
                    prix_unitaire = round(prix / nb_unites, 6) if nb_unites else prix

                    rows.append({
                        "code_nacres"  : code_nom,
                        "designation"  : designation,
                        "code_ijm"     : code_ijm,
                        "prix_ht"      : prix,
                        "condt"        : condt_str,
                        "nb_unites"    : nb_unites,
                        "prix_unitaire": prix_unitaire,
                        "marque"       : marque,
                        "page"         : page_num,
                    })

    return rows

# ── Export CSV ────────────────────────────────────────────────────────────────
FIELDNAMES = [
    "code_nacres", "designation", "code_ijm",
    "prix_ht", "condt", "nb_unites", "prix_unitaire",
    "marque", "page",
]

def export_csv(rows, csv_path):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDNAMES})
    print(f"  → {len(rows)} produits exportés dans {csv_path}")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Lecture du PDF : {PDF_PATH}")
    rows = extract_rows(PDF_PATH)

    if not rows:
        print("ERREUR : aucune ligne extraite. Vérifiez le PDF.")
    else:
        # Aperçu des 5 premières lignes
        print(f"\n{len(rows)} produits trouvés. Aperçu :")
        print(f"{'Code NACRES':<12} {'Prix unit.':<12} {'Condt':<10} {'Désignation'}")
        print("-" * 80)
        for r in rows[:10]:
            print(f"{r['code_nacres']:<12} {r['prix_unitaire']:<12.4f} {r['condt']:<10} {r['designation'][:50]}")

        export_csv(rows, CSV_PATH)
        print(f"\nDate catalogue : {date.today().isoformat()}")
        print("Terminé.")
