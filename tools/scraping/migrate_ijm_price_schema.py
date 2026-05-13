"""
Migrate consumable price columns to a single canonical conditionnement price.

Rules:
    - "Prix du conditionnement" and "Nbr par conditionnement" are the only
      price/packaging columns used by the app.
    - "Source/Signature" is preserved for mass/manual data.
    - Catalogue provenance is stored separately in "Source catalogue IJM".
    - Manually-entered rows keep their manual fields; fuzzy IJM prices are
      moved to separate IJM catalogue rows.
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import date
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
SOLID_PATH = ROOT_DIR / "data" / "mass_factors" / "data_eCO2_masse_consommable.hdf5"
LIQUID_PATH = ROOT_DIR / "data" / "mass_factors" / "data_eCO2_liquides_consommable.hdf5"
MATERIALS_PATH = ROOT_DIR / "data" / "mass_factors" / "empreinte_carbone_materiaux.h5"
TRANSPORT_PATH = ROOT_DIR / "data" / "mass_factors" / "data_transport_origins.hdf5"
PRICE_CSV = ROOT_DIR / "tools" / "scraping" / "output" / "prix_ijm_2025.csv"
AUDIT_PATH = ROOT_DIR / "exports" / "audit_migration_prix_ijm.csv"
REFERENCE_XLSX = ROOT_DIR / "exports" / "données_LABeCO2_reference.xlsx"
OUT_MASSE_CSV = ROOT_DIR / "tools" / "scraping" / "output" / "masses_consommable_with_prix.csv"
OUT_CATALOGUE_CSV = ROOT_DIR / "tools" / "scraping" / "output" / "catalogue_complet.csv"
RUN_DATE = date.today().isoformat()


SOLID_COLUMNS = [
    "Consommable",
    "Marque",
    "Référence",
    "Code CAS",
    "Catégorie",
    "Code NACRES",
    "Masse unitaire (g)",
    "Matériau consommable",
    "Masse unitaire deuxieme materiaux (g)",
    "Matériau deuxieme materiaux",
    "Masse unitaire troisième materiaux (g)",
    "Matériau troisième materiaux",
    "Masse emballage unitaire (g)",
    "Matériau emballage",
    "Masse condionnement (g)",
    "Matériau conditionnement",
    "Nbr par conditionnement",
    "Prix du conditionnement",
    "date d'ajout",
    "Source/Signature",
    "Source catalogue IJM",
    "Lien / Note / Remarque",
    "condt_ijm",
    "designation_ijm",
    "code_ijm",
    "marque_ijm",
    "score_match",
]

LIQUID_COLUMNS = [
    "Produit",
    "Type",
    "Code NACRES",
    "CAS",
    "Référence",
    "Unité",
    "Densité (g/mL)",
    "Concentration (mg/mL)",
    "Facteur CO₂ (kg CO₂e/kg)",
    "Incertitude (%)",
    "Source/Signature",
    "date d'ajout",
    "Note",
    "Volume flacon (mL)",
    "Matériau contenant",
    "Masse contenant (g)",
    "Matériau emballage",
    "Masse emballage (g)",
    "Prix du conditionnement",
    "Nbr par conditionnement",
    "Source catalogue IJM",
    "condt_ijm",
    "designation_ijm",
    "code_ijm",
    "marque_ijm",
    "score_match",
]

MANUAL_SOLID_MARKERS = [
    "Référence",
    "Source/Signature",
    "Lien / Note / Remarque",
    "Matériau consommable",
    "Matériau deuxieme materiaux",
    "Matériau troisième materiaux",
    "Matériau emballage",
    "Matériau conditionnement",
]

LEGACY_CATALOGUE_DATA_COLUMNS = [
    "Masse unitaire (g)",
    "Matériau consommable",
    "Masse unitaire deuxieme materiaux (g)",
    "Matériau deuxieme materiaux",
    "Masse unitaire troisième materiaux (g)",
    "Matériau troisième materiaux",
    "Masse emballage unitaire (g)",
    "Matériau emballage",
    "Masse condionnement (g)",
    "Matériau conditionnement",
]

LEGACY_PRICE_COLUMNS = [
    "prix_ht_ijm",
    "nb_unites_ijm",
    "prix_unitaire_ijm",
]


def clean(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "n/a"} else text


def clean_number(value):
    text = clean(value).replace(",", ".")
    if not text:
        return ""
    try:
        return float(text)
    except ValueError:
        return text


def normalize(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean(value).lower())


def is_nonempty_manual_value(value) -> bool:
    text = clean(value)
    return bool(text)


def is_manual_solid_row(row) -> bool:
    if clean(row.get("Source catalogue IJM", "")) and not clean(row.get("Source/Signature", "")):
        return False
    if (
        clean(row.get("code_ijm", ""))
        and clean(row.get("Consommable", ""))
        and normalize(row.get("Consommable")) == normalize(row.get("designation_ijm"))
        and not clean(row.get("Source/Signature", ""))
    ):
        return False
    return any(is_nonempty_manual_value(row.get(col, "")) for col in MANUAL_SOLID_MARKERS)


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup_path = path.with_suffix(path.suffix + ".backup_before_ijm_price_schema")
    if backup_path.exists():
        return backup_path
    shutil.copy2(path, backup_path)
    return backup_path


def migration_source(path: Path) -> Path:
    backup_path = path.with_suffix(path.suffix + ".backup_before_ijm_price_schema")
    return backup_path if backup_path.exists() else path


def load_price_catalogue() -> pd.DataFrame:
    df = pd.read_csv(PRICE_CSV, dtype=str).fillna("")
    df["code_nacres"] = df["code_nacres"].map(lambda v: clean(v).upper()[:4])
    return df


def source_catalogue(row) -> str:
    page = clean(row.get("page", ""))
    return f"Catalogue IJM 2025, page {page}" if page else "Catalogue IJM 2025"


def catalogue_code(row) -> str:
    return clean(row.get("code_nacres", "") or row.get("Code NACRES", "")).upper()[:4]


def catalogue_packaging_text(row) -> str:
    return f"{clean(row.get('condt', ''))} {clean(row.get('designation', ''))}".casefold().replace(",", ".")


def belongs_to_liquids_catalogue(row) -> bool:
    return catalogue_code(row).startswith("NA") and infer_catalogue_unit(row) == "mL"


def infer_catalogue_unit(row) -> str:
    text = catalogue_packaging_text(row)
    if re.search(r"\d+(?:\.\d+)?\s*(?:µl|μl|ul|ml|millilitres?|milliliters?)\b", text):
        return "mL"
    if re.search(r"\d+(?:\.\d+)?\s*(?:l|litres?|liters?)\b", text):
        return "mL"
    if re.search(r"\d+(?:\.\d+)?\s*kg\b", text) or re.search(r"\d+(?:\.\d+)?\s*g\b", text):
        return "g"
    return ""


def infer_volume_flacon_ml(row):
    text = catalogue_packaging_text(row)
    match_ul = re.search(r"(\d+(?:\.\d+)?)\s*(?:µl|μl|ul)\b", text)
    if match_ul:
        return float(match_ul.group(1)) / 1000.0
    match_ml = re.search(r"(\d+(?:\.\d+)?)\s*(?:ml|millilitres?|milliliters?)\b", text)
    if match_ml:
        return float(match_ml.group(1))
    match_l = re.search(r"(\d+(?:\.\d+)?)\s*(?:l|litres?|liters?)\b", text)
    if match_l:
        return float(match_l.group(1)) * 1000.0
    return ""


def infer_conditionnement_mass_g(row):
    text = catalogue_packaging_text(row)
    match_kg = re.search(r"(\d+(?:\.\d+)?)\s*kg\b", text)
    if match_kg:
        return float(match_kg.group(1)) * 1000.0
    match_g = re.search(r"(\d+(?:\.\d+)?)\s*g\b", text)
    if match_g:
        return float(match_g.group(1))
    return ""


def catalogue_row_from_price(row) -> dict:
    return {
        "Consommable": clean(row.get("designation")),
        "Marque": clean(row.get("marque")),
        "Référence": clean(row.get("code_ijm")),
        "Code CAS": "",
        "Catégorie": "Autres consommables",
        "Code NACRES": clean(row.get("code_nacres")).upper()[:4],
        "Masse unitaire (g)": infer_conditionnement_mass_g(row),
        "Matériau consommable": "",
        "Masse unitaire deuxieme materiaux (g)": "",
        "Matériau deuxieme materiaux": "",
        "Masse unitaire troisième materiaux (g)": "",
        "Matériau troisième materiaux": "",
        "Masse emballage unitaire (g)": "",
        "Matériau emballage": "",
        "Masse condionnement (g)": "",
        "Matériau conditionnement": "",
        "Nbr par conditionnement": clean_number(row.get("nb_unites")),
        "Prix du conditionnement": clean_number(row.get("prix_ht")),
        "date d'ajout": RUN_DATE,
        "Source/Signature": "",
        "Source catalogue IJM": source_catalogue(row),
        "Lien / Note / Remarque": "",
        "condt_ijm": clean(row.get("condt")),
        "designation_ijm": clean(row.get("designation")),
        "code_ijm": clean(row.get("code_ijm")),
        "marque_ijm": clean(row.get("marque")),
        "score_match": "",
    }


def liquid_catalogue_row_from_price(row) -> dict:
    return {
        "Produit": clean(row.get("designation")),
        "Type": "Catalogue IJM",
        "Code NACRES": catalogue_code(row),
        "CAS": "",
        "Référence": clean(row.get("code_ijm")),
        "Unité": infer_catalogue_unit(row),
        "Densité (g/mL)": "",
        "Concentration (mg/mL)": "",
        "Facteur CO₂ (kg CO₂e/kg)": "",
        "Incertitude (%)": "",
        "Source/Signature": "",
        "date d'ajout": RUN_DATE,
        "Note": "",
        "Volume flacon (mL)": infer_volume_flacon_ml(row),
        "Matériau contenant": "",
        "Masse contenant (g)": "",
        "Matériau emballage": "",
        "Masse emballage (g)": "",
        "Prix du conditionnement": clean_number(row.get("prix_ht")),
        "Nbr par conditionnement": clean_number(row.get("nb_unites")),
        "Source catalogue IJM": source_catalogue(row),
        "condt_ijm": clean(row.get("condt")),
        "designation_ijm": clean(row.get("designation")),
        "code_ijm": clean(row.get("code_ijm")),
        "marque_ijm": clean(row.get("marque")),
        "score_match": "",
    }


def merge_legacy_catalogue_data(new_row: dict, legacy_row) -> dict:
    if legacy_row is None:
        return new_row
    for col in LEGACY_CATALOGUE_DATA_COLUMNS:
        value = legacy_row.get(col, "")
        if is_nonempty_manual_value(value):
            new_row[col] = value
    return new_row


def should_merge_exact(manual_row, price_row) -> bool:
    ref_match = normalize(manual_row.get("Référence")) == normalize(price_row.get("code_ijm"))
    if ref_match and normalize(price_row.get("code_ijm")):
        return True
    brand_match = normalize(manual_row.get("Marque")) == normalize(price_row.get("marque"))
    name_match = normalize(manual_row.get("Consommable")) == normalize(price_row.get("designation"))
    return bool(brand_match and name_match)


def migrate_solids(price_df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    df = pd.read_hdf(migration_source(SOLID_PATH))
    price_by_code = {
        clean(row.get("code_ijm")): row
        for _, row in price_df.iterrows()
        if clean(row.get("code_ijm"))
    }

    migrated_rows = []
    audit_rows = []
    merged_codes = set()
    legacy_catalogue_by_code = {}

    for _, row in df.iterrows():
        code = clean(row.get("code_ijm", ""))
        if code and not is_manual_solid_row(row):
            legacy_catalogue_by_code.setdefault(code, row)

    for idx, row in df.iterrows():
        if not is_manual_solid_row(row):
            continue

        new_row = {col: row.get(col, "") for col in SOLID_COLUMNS}
        old_ijm_code = clean(row.get("code_ijm", ""))
        old_ijm_price = clean(row.get("prix_ht_ijm", ""))
        old_manual_price = clean(row.get("Prix du conditionnement", ""))
        exact_price = price_by_code.get(old_ijm_code)
        if exact_price is not None and belongs_to_liquids_catalogue(exact_price):
            exact_price = None

        if exact_price is not None and should_merge_exact(row, exact_price):
            new_row.update(catalogue_row_from_price(exact_price))
            for col in MANUAL_SOLID_MARKERS:
                new_row[col] = row.get(col, "")
            new_row["Consommable"] = row.get("Consommable", "")
            new_row["Marque"] = row.get("Marque", "")
            new_row["Référence"] = row.get("Référence", "")
            new_row["Source/Signature"] = row.get("Source/Signature", "")
            new_row["Lien / Note / Remarque"] = row.get("Lien / Note / Remarque", "")
            merged_codes.add(old_ijm_code)
            action = "manuel_match_exact_prix_catalogue_conserve"
        else:
            new_row["Prix du conditionnement"] = clean_number(old_manual_price)
            new_row["Source catalogue IJM"] = ""
            new_row["condt_ijm"] = ""
            new_row["designation_ijm"] = ""
            new_row["code_ijm"] = ""
            new_row["marque_ijm"] = ""
            new_row["score_match"] = ""
            action = "manuel_conserve_prix_catalogue_separe" if old_ijm_price else "manuel_conserve"

        migrated_rows.append(new_row)
        audit_rows.append({
            "type": "solide",
            "action": action,
            "index_source": idx,
            "consommable": clean(row.get("Consommable")),
            "marque": clean(row.get("Marque")),
            "reference": clean(row.get("Référence")),
            "code_nacres": clean(row.get("Code NACRES")),
            "ancien_prix_conditionnement": old_manual_price,
            "ancien_prix_ht_ijm": old_ijm_price,
            "code_ijm": old_ijm_code,
            "score_match": clean(row.get("score_match")),
        })

    for _, row in price_df.iterrows():
        if belongs_to_liquids_catalogue(row):
            continue
        code_ijm = clean(row.get("code_ijm"))
        if code_ijm and code_ijm in merged_codes:
            continue
        new_row = catalogue_row_from_price(row)
        legacy_row = legacy_catalogue_by_code.get(code_ijm)
        new_row = merge_legacy_catalogue_data(new_row, legacy_row)
        has_legacy_mass = any(
            is_nonempty_manual_value(new_row.get(col, ""))
            for col in LEGACY_CATALOGUE_DATA_COLUMNS
        )
        migrated_rows.append(new_row)
        audit_rows.append({
            "type": "solide",
            "action": (
                "catalogue_ijm_ligne_separee_donnees_masse_conservees"
                if has_legacy_mass else
                "catalogue_ijm_ligne_separee"
            ),
            "index_source": "",
            "consommable": new_row["Consommable"],
            "marque": new_row["Marque"],
            "reference": new_row["Référence"],
            "code_nacres": new_row["Code NACRES"],
            "ancien_prix_conditionnement": "",
            "ancien_prix_ht_ijm": new_row["Prix du conditionnement"],
            "code_ijm": new_row["code_ijm"],
            "score_match": "",
        })

    out = pd.DataFrame(migrated_rows).reindex(columns=SOLID_COLUMNS)
    return out, audit_rows


def migrate_liquids(price_df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    if not LIQUID_PATH.exists():
        return pd.DataFrame(columns=LIQUID_COLUMNS), []

    df = pd.read_hdf(migration_source(LIQUID_PATH))
    price_by_code = {
        clean(row.get("code_ijm")): row
        for _, row in price_df.iterrows()
        if clean(row.get("code_ijm"))
    }
    audit_rows = []
    migrated_rows = []

    for idx, row in df.iterrows():
        new_row = {col: row.get(col, "") for col in LIQUID_COLUMNS}
        old_price = clean(row.get("prix_ht_ijm", "")) or clean(row.get("Prix du conditionnement", ""))
        old_nb = clean(row.get("nb_unites_ijm", "")) or clean(row.get("Nbr par conditionnement", ""))
        if not clean(new_row.get("Prix du conditionnement")):
            new_row["Prix du conditionnement"] = clean_number(old_price)
        if not clean(new_row.get("Nbr par conditionnement")):
            new_row["Nbr par conditionnement"] = clean_number(old_nb)

        code_ijm = clean(row.get("code_ijm", ""))
        if old_price and not clean(new_row.get("Source catalogue IJM")):
            price_row = price_by_code.get(code_ijm)
            new_row["Source catalogue IJM"] = (
                source_catalogue(price_row) if price_row is not None else "Catalogue IJM 2025"
            )
        if clean(new_row.get("Source catalogue IJM", "")) and not clean(new_row.get("date d'ajout", "")):
            new_row["date d'ajout"] = RUN_DATE

        migrated_rows.append(new_row)
        if old_price:
            audit_rows.append({
                "type": "liquide",
                "action": "liquide_prix_catalogue_migre",
                "index_source": idx,
                "consommable": clean(row.get("Produit")),
                "marque": clean(row.get("marque_ijm")),
                "reference": clean(row.get("Référence")),
                "code_nacres": clean(row.get("Code NACRES")),
                "ancien_prix_conditionnement": clean(row.get("Prix du conditionnement", "")),
                "ancien_prix_ht_ijm": old_price,
                "code_ijm": code_ijm,
                "score_match": clean(row.get("score_match")),
            })

    existing_codes = {
        clean(row.get("code_ijm", ""))
        for row in migrated_rows
        if clean(row.get("code_ijm", ""))
    }
    existing_products = {
        (clean(row.get("Code NACRES", "")).upper()[:4], normalize(row.get("Produit", "")))
        for row in migrated_rows
        if clean(row.get("Produit", ""))
    }

    for _, row in price_df.iterrows():
        if not belongs_to_liquids_catalogue(row):
            continue
        code_ijm = clean(row.get("code_ijm"))
        product_key = (catalogue_code(row), normalize(row.get("designation", "")))
        if (code_ijm and code_ijm in existing_codes) or product_key in existing_products:
            continue

        new_row = liquid_catalogue_row_from_price(row)
        migrated_rows.append(new_row)
        if code_ijm:
            existing_codes.add(code_ijm)
        existing_products.add(product_key)
        audit_rows.append({
            "type": "liquide",
            "action": "catalogue_ijm_ligne_liquides_solvents",
            "index_source": "",
            "consommable": new_row["Produit"],
            "marque": new_row["marque_ijm"],
            "reference": new_row["Référence"],
            "code_nacres": new_row["Code NACRES"],
            "ancien_prix_conditionnement": "",
            "ancien_prix_ht_ijm": new_row["Prix du conditionnement"],
            "code_ijm": new_row["code_ijm"],
            "score_match": "",
        })

    out = pd.DataFrame(migrated_rows).reindex(columns=LIQUID_COLUMNS)
    return out, audit_rows


def write_reference_excel(solid_df: pd.DataFrame, liquid_df: pd.DataFrame) -> None:
    REFERENCE_XLSX.parent.mkdir(parents=True, exist_ok=True)
    materials = pd.read_hdf(MATERIALS_PATH) if MATERIALS_PATH.exists() else pd.DataFrame()
    transport = pd.read_hdf(TRANSPORT_PATH) if TRANSPORT_PATH.exists() else pd.DataFrame()
    with pd.ExcelWriter(REFERENCE_XLSX, engine="openpyxl") as writer:
        solid_df.to_excel(writer, sheet_name="Consommables (masse)", index=False)
        liquid_df.to_excel(writer, sheet_name="Liquides & Solvants", index=False)
        materials.to_excel(writer, sheet_name="Matériaux", index=False)
        transport.to_excel(writer, sheet_name="Transport", index=False)


def main() -> None:
    if not PRICE_CSV.exists():
        raise FileNotFoundError(f"Catalogue IJM introuvable: {PRICE_CSV}")

    price_df = load_price_catalogue()
    SOLID_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIQUID_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)

    solid_backup = backup(SOLID_PATH)
    liquid_backup = backup(LIQUID_PATH)
    reference_backup = backup(REFERENCE_XLSX)

    solid_df, solid_audit = migrate_solids(price_df)
    liquid_df, liquid_audit = migrate_liquids(price_df)
    audit_df = pd.DataFrame(solid_audit + liquid_audit)

    solid_df.to_hdf(SOLID_PATH, key="data", mode="w", complevel=5)
    if not liquid_df.empty:
        liquid_df.to_hdf(LIQUID_PATH, key="data", mode="w", complevel=5)
    OUT_CATALOGUE_CSV.parent.mkdir(parents=True, exist_ok=True)
    solid_df.to_csv(OUT_CATALOGUE_CSV, index=False, encoding="utf-8")
    manual_mask = solid_df["Source catalogue IJM"].fillna("").astype(str).str.strip() == ""
    solid_df[manual_mask].to_csv(OUT_MASSE_CSV, index=False, encoding="utf-8")
    audit_df.to_csv(AUDIT_PATH, index=False, encoding="utf-8")
    write_reference_excel(solid_df, liquid_df)

    print("Migration prix IJM terminee.")
    print(f"  Solides : {len(solid_df)} lignes -> {SOLID_PATH}")
    print(f"  Liquides: {len(liquid_df)} lignes -> {LIQUID_PATH}")
    print(f"  Audit   : {len(audit_df)} lignes -> {AUDIT_PATH}")
    print(f"  Export  : {REFERENCE_XLSX}")
    print(f"  CSV     : {OUT_CATALOGUE_CSV}")
    if solid_backup:
        print(f"  Backup solides : {solid_backup}")
    if liquid_backup:
        print(f"  Backup liquides: {liquid_backup}")
    if reference_backup:
        print(f"  Backup export  : {reference_backup}")


if __name__ == "__main__":
    main()
