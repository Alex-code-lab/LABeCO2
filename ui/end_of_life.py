# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026, LABeCO2, Alexandre Souchaud.
"""
Routage des consommables vers leur filière de fin de vie (DASRI / DIS) à partir
du code NACRES, et résolution du facteur d'émission correspondant en base.

Modèle :
  - Les consommables (utilisés en manip) partent en filière contaminée :
    DASRI pour la bio/santé, DIS pour la chimie.
  - Les emballages et conditionnements ne sont PAS contaminés : ils suivent
    leur facteur EoL par matériau (cf. materials.eol_emission_factor_id).

Hypothèse conservative : si la filière ne peut pas être déterminée à partir du
NACRES, on retombe sur DASRI (facteur le plus élevé → surestime, plutôt que
de sous-estimer un impact réel).
"""

from __future__ import annotations

# ── Filières ──────────────────────────────────────────────────────────────────

FILIERE_DASRI = "DASRI"   # Déchets d'Activités de Soins à Risque Infectieux
FILIERE_DIS = "DIS"       # Déchets Industriels Spéciaux (chimie)
FILIERE_DEFAULT = FILIERE_DASRI

# ── Routage NACRES → filière ──────────────────────────────────────────────────
# Basé sur l'analyse des intitulés de la nomenclature NACRES (achats publics FR).
# Préfixes 2 caractères. Non listé → FILIERE_DEFAULT (DASRI, conservatif).
NACRES_FILIERE_ROUTING: dict[str, str] = {
    "NA": FILIERE_DIS,     # Solvants, produits chimiques
    "NB": FILIERE_DASRI,   # Consommables paillasse (ambigu, défaut bio)
    "NC": FILIERE_DASRI,   # Biomolécules, électrophorèse, biologie
    "ND": FILIERE_DASRI,   # Maintenance équipement (peu de consommables)
    "NE": FILIERE_DASRI,   # Services biologie
    "NL": FILIERE_DIS,     # Matières premières chimiques
    "NM": FILIERE_DIS,     # Produits chimiques
}

# ── Mapping filière → nom du facteur EoL en base ──────────────────────────────
# Les noms doivent correspondre exactement à ceux insérés par la migration v3.
FILIERE_TO_FACTOR_NAME: dict[str, str] = {
    FILIERE_DASRI: "DAS/Incinération - Impacts (ADEME)",
    FILIERE_DIS:   "DIS/Incinération - Impacts (ADEME)",
}


def filiere_for_nacres(code: str | None) -> str:
    """Retourne 'DASRI' ou 'DIS' pour un code NACRES donné.

    Le routage se fait sur le préfixe 2 caractères (insensible à la casse).
    Renvoie FILIERE_DEFAULT si le code est vide, inconnu ou non listé.
    """
    if not code:
        return FILIERE_DEFAULT
    prefix = str(code).strip().upper()[:2]
    return NACRES_FILIERE_ROUTING.get(prefix, FILIERE_DEFAULT)


def factor_name_for_nacres(code: str | None) -> str:
    """Raccourci : retourne directement le nom du facteur EoL en base."""
    return FILIERE_TO_FACTOR_NAME[filiere_for_nacres(code)]
