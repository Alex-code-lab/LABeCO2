"""
parse_catalogue.py
Parser générique de catalogues fournisseurs PDF → CSV.

Usage :
    python parse_catalogue.py --fournisseur IJM
    python parse_catalogue.py --fournisseur VWR --pdf /chemin/catalogue.pdf
    python parse_catalogue.py --pdf /chemin/catalogue.pdf --out /chemin/output.csv

Fournisseurs préconfigurés : voir CONFIGS ci-dessous.
Pour un nouveau fournisseur, ajoutez une entrée dans CONFIGS.

Colonnes CSV de sortie :
    code_nacres    - Code NACRES (2 lettres + 2 chiffres), vide si non applicable
    designation    - Nom du produit (nettoyé)
    code_fournisseur - Référence interne fournisseur
    prix_ht        - Prix HT par conditionnement (€)
    condt          - Conditionnement brut (ex. "1 x 200")
    nb_unites      - Nombre d'unités dans le conditionnement
    prix_unitaire  - Prix HT par unité
    marque         - Marque / fabricant
    fournisseur    - Nom du fournisseur (depuis la config)
    page           - Numéro de page dans le PDF
"""

import os
import re
import csv
import argparse
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
import pdfplumber

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # data/catalogues/


# ── Config fournisseur ────────────────────────────────────────────────────────

@dataclass
class SupplierConfig:
    """Décrit comment parser le catalogue d'un fournisseur donné."""
    name: str
    pdf_path: str
    output_csv: str

    # ── Détection par en-têtes (prioritaire si renseigné) ─────────────────
    # Clé : texte d'en-tête attendu (insensible à la casse, partial match)
    # Valeur : champ standard parmi : designation, code_fournisseur,
    #          prix_ht, condt, code_nacres, marque
    header_map: dict = field(default_factory=dict)

    # ── Détection par patterns regex (fallback sans en-têtes) ─────────────
    has_nacres: bool = True
    code_nacres_re: str = r'^[A-Z]{2}\d{2,3}$'
    code_supplier_re: str = r'^[A-Za-z]{1,5}\d{2,6}[A-Za-z0-9]*$'
    prix_re: str = r'^\d{1,6}[,\.]\d{2}$'
    noise_re: str = r'\bSur\s+Cde\b|\bNouveau\b|\bSupprimé\b.*'
    min_cols: int = 4

    # Date ou période du catalogue (ex. "2025", "2010-2012") — informatif
    catalogue_date: str = ""

    # ── Extracteur texte personnalisé (pour PDF non tabulaires) ───────────
    # Si renseigné, court-circuite toute la logique tableau et appelle
    # cette fonction avec (cfg) → list[dict]. Voir _extract_duchefa().
    custom_extractor: object = None  # Callable[[SupplierConfig], list[dict]]


# ── Configurations préconfigurées ─────────────────────────────────────────────

def _supplier_dir(name: str) -> str:
    """Retourne le chemin du dossier d'un fournisseur dans data/catalogues/."""
    return os.path.join(BASE_DIR, name)


CONFIGS: dict[str, SupplierConfig] = {
    "IJM": SupplierConfig(
        name="IJM",
        pdf_path=os.path.join(_supplier_dir("IJM"), "Catalogue_IJM_2025.pdf"),
        output_csv=os.path.join(_supplier_dir("IJM"), "prix_ijm_2025.csv"),
        has_nacres=True,
        catalogue_date="2025",
    ),

    "DUCHEFA": SupplierConfig(
        name="DUCHEFA",
        pdf_path=os.path.join(_supplier_dir("DUCHEFA"), "Duchefa-catalogue.pdf"),
        output_csv=os.path.join(_supplier_dir("DUCHEFA"), "prix_duchefa.csv"),
        has_nacres=False,
        catalogue_date="2010-2012",
        # custom_extractor assigné après définition de _extract_duchefa (voir bas du fichier)
    ),

    # ── Ajouter un nouveau fournisseur ────────────────────────────────────
    # 1. Créer data/catalogues/NOM_FOURNI/  et y déposer le PDF
    # 2. Copier le bloc ci-dessous, adapter les champs
    # 3. Si le PDF a des en-têtes de colonnes → renseigner header_map
    #    Sinon → ajuster code_supplier_re / prix_re selon le format
    #
    # "VWR": SupplierConfig(
    #     name="VWR",
    #     pdf_path=os.path.join(_supplier_dir("VWR"), "Catalogue_VWR_2026.pdf"),
    #     output_csv=os.path.join(_supplier_dir("VWR"), "prix_vwr_2026.csv"),
    #     has_nacres=False,
    #     catalogue_date="2026",
    #     header_map={
    #         "description": "designation",
    #         "cat. no.":    "code_fournisseur",
    #         "pack size":   "condt",
    #         "price":       "prix_ht",
    #         "brand":       "marque",
    #     },
    # ),
}


# ── Utilitaires ────────────────────────────────────────────────────────────────

def clean_text(s: str, noise_re: str) -> str:
    if not s:
        return ""
    return re.sub(noise_re, "", s, flags=re.IGNORECASE).strip(" -")


_CONDT_RE = re.compile(r'(\d+)\s*[xX×]\s*(\d+)')


def parse_nb_unites(condt_str: str) -> int:
    if not condt_str:
        return 1
    s = condt_str.strip()
    if re.search(r'\d\s*[xX×]\s*\d+\s*[A-Za-z]', s):
        return 1
    m = _CONDT_RE.search(s)
    if m:
        return int(m.group(1)) * int(m.group(2))
    m2 = re.match(r'^(\d+)$', s.strip())
    if m2:
        return int(m2.group(1))
    return 1


def parse_prix(s: str) -> Optional[float]:
    if not s:
        return None
    try:
        v = float(re.sub(r'[^\d.,]', '', s).replace(',', '.'))
        return v if v > 0 else None
    except ValueError:
        return None


# ── Détection par en-têtes ────────────────────────────────────────────────────

def detect_header_row(
    table: list, header_map: dict
) -> tuple[Optional[dict[int, str]], Optional[int]]:
    """
    Cherche une ligne d'en-tête dans les 5 premières lignes de la table.
    Retourne (col_map, row_idx) ou (None, None).
    col_map : {index_colonne: nom_champ_standard}
    """
    keys = {k.lower(): v for k, v in header_map.items()}
    for row_idx, row in enumerate(table[:5]):
        if row is None:
            continue
        cells = [c.lower().strip() if c else "" for c in row]
        mapping = {}
        for i, cell in enumerate(cells):
            for header_key, field_name in keys.items():
                if header_key in cell:
                    mapping[i] = field_name
                    break
        if len(mapping) >= 2:
            return mapping, row_idx
    return None, None


def row_from_headers(
    cells: list[str], col_map: dict[int, str], cfg: SupplierConfig
) -> Optional[dict]:
    """Extrait une ligne produit en utilisant les positions de colonnes connues."""
    extracted: dict[str, str] = {}
    for i, field_name in col_map.items():
        extracted[field_name] = cells[i].strip() if i < len(cells) and cells[i] else ""

    prix = parse_prix(extracted.get("prix_ht", ""))
    if prix is None:
        return None
    designation = clean_text(extracted.get("designation", ""), cfg.noise_re)
    if not designation or len(designation) < 3:
        return None

    nb_unites = parse_nb_unites(extracted.get("condt", ""))
    return {
        "code_nacres"     : extracted.get("code_nacres", ""),
        "designation"     : designation,
        "code_fournisseur": extracted.get("code_fournisseur", ""),
        "prix_ht"         : prix,
        "condt"           : extracted.get("condt", ""),
        "nb_unites"       : nb_unites,
        "prix_unitaire"   : round(prix / nb_unites, 6) if nb_unites else prix,
        "marque"          : extracted.get("marque", ""),
    }


# ── Détection par patterns (fallback) ────────────────────────────────────────

def row_from_patterns(cells: list[str], cfg: SupplierConfig) -> Optional[dict]:
    """Identifie les champs d'une ligne en cherchant des patterns connus dans chaque cellule."""
    re_nacres   = re.compile(cfg.code_nacres_re)
    re_supplier = re.compile(cfg.code_supplier_re)
    re_prix     = re.compile(cfg.prix_re)

    designation = code_fournisseur = prix_str = condt_str = code_nacres = marque = ""

    for i, cell in enumerate(cells):
        c = cell.strip()

        if cfg.has_nacres and re_nacres.match(c) and not code_nacres:
            code_nacres = c
            if i + 1 < len(cells):
                marque = clean_text(cells[i + 1], cfg.noise_re)

        elif re_supplier.match(c) and not code_fournisseur:
            code_fournisseur = c
            if i > 0 and cells[i - 1]:
                designation = clean_text(cells[i - 1], cfg.noise_re)

        elif re_prix.match(c) and not prix_str:
            prix_str = c
            if i + 1 < len(cells):
                condt_str = cells[i + 1]

    # Désignation de secours : première cellule qui ressemble à du texte
    if not designation:
        for cell in cells:
            c = clean_text(cell, cfg.noise_re)
            if c and not re_nacres.match(c) and not re_supplier.match(c) and not re_prix.match(c):
                designation = c
                break

    prix = parse_prix(prix_str)
    if prix is None:
        return None
    if cfg.has_nacres and not code_nacres:
        return None
    if not designation or len(designation) < 3:
        return None
    if designation.upper() in ("DESIGNATION", "CODE IJM", "PRIX HT", "CODE NOM"):
        return None

    nb_unites = parse_nb_unites(condt_str)
    return {
        "code_nacres"     : code_nacres,
        "designation"     : designation,
        "code_fournisseur": code_fournisseur,
        "prix_ht"         : prix,
        "condt"           : condt_str,
        "nb_unites"       : nb_unites,
        "prix_unitaire"   : round(prix / nb_unites, 6) if nb_unites else prix,
        "marque"          : marque,
    }


# ── Extracteur texte Duchefa ──────────────────────────────────────────────────
#
# Structure du catalogue Duchefa :
#   - Produits décrits en texte libre (pas de tableau), 2 colonnes par page
#   - Référence : lettre + 4 chiffres, ex. "C 0506" (avec espace dans le PDF)
#   - Ligne prix : "C0506.1000 1 kg € 16,00"
#   - Index alphabétique en fin de catalogue (pages ~187-194)

_DUCHEFA_PRICE_RE = re.compile(
    r'([A-Z])\s?(\d{4})'                                     # base cat_no (lettre + 4 chiffres)
    r'(\.\d{3,5})'                                            # code pack capturé (.0100, .1000…)
    r'\s+([\d,\.]+\s*'                                        # quantité
    r'(?:g|kg|mg|ml|mL|µg|µl|litre?s?|IU|U|nmol|mmol|µmol|unit)s?)'  # unité
    r'\s+€\s*([\d,]+)',                                       # prix
    re.IGNORECASE,
)

# Entrée d'index : cat_no  [CAS]  page  (le CAS est absent pour les milieux sans n° CAS)
_DUCHEFA_IDX_RE = re.compile(
    r'([A-Z]\d{4})'             # cat_no (sans espace dans l'index)
    r'(?:\s+[\d/\-\.]+)?'       # CAS optionnel (peut être "7758-99-8" ou absent)
    r'\s+(\d{1,3})\b',          # numéro de page (1-3 chiffres)
)

# Pages de l'index alphabétique (contiennent "Cat. no." dans le texte)
_IDX_HEADER = re.compile(r'Cat\.\s*no\.', re.IGNORECASE)


def _parse_duchefa_index(pdf) -> dict[str, str]:
    """Retourne {cat_no: nom_produit} depuis les pages d'index."""
    names: dict[str, str] = {}

    for page in pdf.pages:
        text = page.extract_text() or ""
        if not _IDX_HEADER.search(text):
            continue

        # Parcours ligne par ligne
        for line in text.splitlines():
            prev_end = 0
            for m in _DUCHEFA_IDX_RE.finditer(line):
                cat_no = m.group(1)
                # Le nom est le texte entre la fin du match précédent et le début du cat_no
                raw_name = line[prev_end:m.start()].strip(" \t,")
                # Nettoyer : enlever les restes du précédent cat_no/CAS/page en début
                raw_name = re.sub(r'^[\d/\-\.\s]+', '', raw_name).strip()
                if raw_name and len(raw_name) > 2 and cat_no not in names:
                    names[cat_no] = raw_name
                prev_end = m.end()  # group(2) est maintenant la page (CAS optionnel)

    return names


def _extract_duchefa(cfg: SupplierConfig) -> list[dict]:
    """Extracteur texte pour le catalogue Duchefa (pas de tableau structuré)."""
    rows = []

    with pdfplumber.open(cfg.pdf_path) as pdf:
        print(f"  Pass 1 : lecture de l'index…")
        names = _parse_duchefa_index(pdf)
        print(f"  → {len(names)} produits trouvés dans l'index")

        print(f"  Pass 2 : extraction des prix ({len(pdf.pages)} pages)…")
        seen: set[tuple] = set()  # (cat_no, condt) pour déduplication

        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for m in _DUCHEFA_PRICE_RE.finditer(text):
                base_ref  = m.group(1) + m.group(2)        # "C0506"
                pack_code = m.group(3)                      # ".1000"
                cat_no    = base_ref + pack_code            # "C0506.1000" — référence complète
                condt     = m.group(4).strip()
                prix      = parse_prix(m.group(5))
                if prix is None:
                    continue
                if cat_no in seen:
                    continue
                seen.add(cat_no)

                designation = names.get(base_ref, "")  # index indexé par base_ref sans pack
                rows.append({
                    "code_nacres"     : "",
                    "designation"     : designation,
                    "code_fournisseur": cat_no,
                    "prix_ht"         : prix,
                    "condt"           : condt,
                    "nb_unites"       : 1,
                    "prix_unitaire"   : prix,
                    "marque"          : "Duchefa Biochemie",
                    "fournisseur"     : cfg.name,
                    "catalogue_date"  : cfg.catalogue_date,
                    "page"            : page_num,
                })

    # Trier par cat_no puis conditionnement pour lisibilité
    rows.sort(key=lambda r: (r["code_fournisseur"], r["condt"]))
    return rows


# Assignation tardive : _extract_duchefa est définie après CONFIGS
CONFIGS["DUCHEFA"].custom_extractor = _extract_duchefa


# ── Extraction principale ─────────────────────────────────────────────────────

def extract_rows(cfg: SupplierConfig) -> list[dict]:
    if cfg.custom_extractor is not None:
        return cfg.custom_extractor(cfg)

    rows = []
    use_headers = bool(cfg.header_map)

    with pdfplumber.open(cfg.pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue

                col_map, header_row_idx = (
                    detect_header_row(table, cfg.header_map) if use_headers
                    else (None, None)
                )

                for row_idx, raw_row in enumerate(table):
                    if raw_row is None or row_idx == header_row_idx:
                        continue
                    cells = [c.strip() if c else "" for c in raw_row]
                    if len(cells) < cfg.min_cols:
                        continue

                    result = (
                        row_from_headers(cells, col_map, cfg) if col_map is not None
                        else row_from_patterns(cells, cfg)
                    )
                    if result:
                        result["fournisseur"]     = cfg.name
                        result["catalogue_date"]  = cfg.catalogue_date
                        result["page"]            = page_num
                        rows.append(result)

    return rows


# ── Export CSV ─────────────────────────────────────────────────────────────────

FIELDNAMES = [
    "code_nacres", "designation", "code_fournisseur",
    "prix_ht", "condt", "nb_unites", "prix_unitaire",
    "marque", "fournisseur", "catalogue_date", "page",
]


def export_csv(rows: list[dict], csv_path: str) -> None:
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDNAMES})
    print(f"  → {len(rows)} produits exportés dans {csv_path}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Parse un catalogue fournisseur PDF → CSV")
    parser.add_argument(
        "--fournisseur", choices=list(CONFIGS.keys()),
        help=f"Fournisseur préconfiguré ({', '.join(CONFIGS.keys())})"
    )
    parser.add_argument("--pdf", help="Chemin vers le PDF (si fournisseur non préconfiguré)")
    parser.add_argument("--out", help="Chemin CSV de sortie")
    args = parser.parse_args()

    if args.fournisseur:
        cfg = CONFIGS[args.fournisseur]
        if args.pdf:
            cfg.pdf_path = args.pdf
        if args.out:
            cfg.output_csv = args.out
    elif args.pdf:
        # PDF hors config : le CSV est déposé dans le même dossier que le PDF
        name = os.path.splitext(os.path.basename(args.pdf))[0]
        pdf_dir = os.path.dirname(os.path.abspath(args.pdf))
        cfg = SupplierConfig(
            name=name,
            pdf_path=args.pdf,
            output_csv=args.out or os.path.join(pdf_dir, f"prix_{name.lower()}.csv"),
        )
    else:
        # Défaut : IJM (compatibilité avec l'ancien parse_catalogue_ijm.py)
        cfg = CONFIGS["IJM"]

    print(f"Fournisseur : {cfg.name}")
    print(f"PDF         : {cfg.pdf_path}")
    print(f"Sortie      : {cfg.output_csv}")
    print(f"Mode        : {'en-têtes' if cfg.header_map else 'patterns regex'}")

    rows = extract_rows(cfg)
    if not rows:
        print("\nERREUR : aucune ligne extraite.")
        print("Conseils :")
        print("  - Vérifiez que le PDF contient du texte (pas un scan image)")
        print("  - Ajoutez un header_map si le catalogue a des en-têtes de colonnes")
        print("  - Ajustez code_supplier_re / code_nacres_re si les patterns diffèrent")
        return

    print(f"\n{len(rows)} produits trouvés. Aperçu :")
    print(f"{'NACRES':<10} {'Fournisseur':<12} {'Prix unit.':<12} {'Condt':<10} {'Désignation'}")
    print("-" * 90)
    for r in rows[:10]:
        print(
            f"{r['code_nacres']:<10} {r['fournisseur']:<12} "
            f"{r['prix_unitaire']:<12.4f} {r['condt']:<10} {r['designation'][:45]}"
        )

    export_csv(rows, cfg.output_csv)
    print(f"\nDate : {date.today().isoformat()}")


if __name__ == "__main__":
    main()
