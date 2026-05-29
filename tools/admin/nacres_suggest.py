# SPDX-License-Identifier: GPL-3.0-or-later
"""Suggestions prudentes de codes NACRES par mots-clés produit."""

from __future__ import annotations


# Règles ordonnées : la première qui matche l'emporte.
# Tuple (keywords_lower, nacres_code, label_raison)
_NACRES_RULES: list[tuple[list[str], str, str]] = [
    (
        ["gant", "gants", "glove", "gloves", "nitrile", "latex powder", "latex glove"],
        "HA01",
        "gants / EPI",
    ),
    (
        [
            "cellulase", "macerozyme", "pectolyase", "zymolyase", "protease",
            "lipase", "amylase", "nuclease", "lysozyme", "pectinase",
        ],
        "NA52",
        "enzyme",
    ),
    (
        [
            "mycin", "cillin", "cycline", "cyclin", "oxacin", "floxacin",
            "amphotericin", "cefotaxime", "cephalexin", "trimethoprim",
            "sulphamethoxazole", "chloramphenicol", "phleomycin", "zeocin",
            "bleomycin", "metronidazole", "miconazole", "griseofulvin",
            "cetrimide", "cetrimonium", "chlorhexidine", "chloroxylenol",
            "thimerosal", "rifamp", "colistin", "bacitracin", "acyclovir",
            "ribavirin", "cycloheximide", "validamycin", "doxorubicin",
            "fluoro uracil", "5-foa", "chlorsulfuron", "phosphinotricin",
            "paromomycin", "nalidixic", "g-418", "d-cycloserine", "carboxin",
            "mercaptopurine", "methotrexate",
        ],
        "NA76",
        "antibiotique/antimicrobien",
    ),
    (
        [
            "medium", "media", "broth", "murashige", "skoog", " ms ", "b5 ",
            "plant agar", "micro agar", "phyto agar", "daishin agar",
            "malt agar", "malt extract", "luria", "peptone", "yeast extract",
            "gelrite", "gelcarin", "carrageenan", "agarose", "low melting",
            "seaplaque", "vitamin mixture", "salt mixture", "soya peptone",
            "casein hydrolysate",
        ],
        "NA71",
        "milieu de culture / gélifiant",
    ),
    (["agar"], "NA71", "gélifiant"),
    (
        [
            "dimethylsulfoxide", "dmso", "ethanol", "methanol", "acetone",
            "isopropanol", "propanol", "glycerol", "glycerin",
        ],
        "NA03",
        "solvant non halogéné",
    ),
    (
        [
            "hydrochloric acid", "sulphuric acid", "nitric acid",
            "phosphoric acid", "perchloric acid", "acetic acid glacial",
        ],
        "NA04",
        "acide",
    ),
    (["sodium hydroxide", "potassium hydroxide", "naoh", "koh"], "NA05", "base"),
    (
        [
            "chloride", "sulphate", "sulfate", "nitrate", "phosphate",
            "hydroxide", "carbonate", "citrate", "gluconate", "molybdate",
            "thiosulphate", "edta", "fenaedta", "ferrous", "cupric",
            "aluminium", "cobalt", "manganese", "magnesium", "ammonium",
            "silver nitrate", "zinc sulphate", "boric acid", "potassium iodide",
            "sodium alginate", "sodium dodecyl", "sds",
        ],
        "NA21",
        "sel inorganique / minéral",
    ),
    (
        [
            "l-alanine", "l-arginine", "l-asparagine", "l-aspartic",
            "l-cysteine", "l-glutamine", "l-glutamic", "l-histidine",
            "l-isoleucine", "l-leucine", "l-lysine", "l-methionine",
            "l-ornithine", "l-phenylalanine", "l-proline", "l-serine",
            "l-threonine", "l-tryptophan", "l-tyrosine", "l-valine",
            "glycine", "amino acid", "thiamine", "pyridoxine",
            "nicotinic acid", "nicotinamide", "folic acid", "folinate",
            "biotin", "biotine", "choline", "cyanocobalamin", "pantothenate",
            "inositol", "riboflavin", "ascorbic acid", "p-aminobenzoic",
            "sucrose", "glucose", "fructose", "galactose", "mannose",
            "mannitol", "sorbitol", "ribose", "lactose", "maltose",
            "trehalose", "raffinose", "xylose", "kinetin", "zeatin",
            "benzylaminopurine", "6-bap", "bap", "indole-3-acetic", "iaa",
            "indole-3-butyric", "iba", "naphthalene acetic", "naa",
            "gibberellic", "gibberellin", "abscisic", "thidiazuron", "cppu",
            "meta-topoline", "picloram", "dicamba", "2,4-d", "2,4 d",
            "4-cpa", "paclobutrazol", "flurprimidol", "fluridon", "oryzaline",
            "colchicine", "epibrassinolide", "methyl jasmonate", "jasmonic acid",
            "salicylic acid", "hepes", "mes ", "mops", "tris", "pipes",
            "bes ", "bis-tris", "triethanolamine", "taurine", "spermidine",
            "citric acid", "malic acid", "acetylsalicylic", "polyethylene glycol",
            "peg ", "peg4", "peg6", "dithioerythreitol", "dte", "gluthatione",
            "charcoal activated", "starch", "dextran sulphate", "adenine",
            "adenosine", "atp", "iptg", "x-gal", "x-phos", "x-glca",
            "blue-gal", "salmon gal", "mug ", "ntb", "bcip", "guanidine",
            "hydroxyquinoline", "fluoroorotic", "atrazine", "bromoxynil",
            "trifluralin", "amiprophos", "maleic hydrazide", "dicamba",
            "absisic", "naphtalene acetic", "naphtoxyacetic", "triiodobenzoic",
            "trichlorophenoxyacetic", "chlorophenoxyacetic", "riboside",
            "chaps", "bes", "luciferin", "mtt", "esculin", "nitrophenyl",
            "urea", "thimerosal",
        ],
        "NA25",
        "réactif organique",
    ),
]


def suggest_nacres(name: str) -> tuple[str, str]:
    """Retourne ``(code_nacres, raison)`` depuis un nom produit."""
    name_l = f" {name.lower()} "
    for keywords, code, reason in _NACRES_RULES:
        if any(keyword in name_l for keyword in keywords):
            return code, reason
    return "", ""
