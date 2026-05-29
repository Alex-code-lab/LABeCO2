# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests de classification des fusions admin."""

from tools.admin.merge_analyzer import business_key, classify_row


def test_business_key_uses_reference_for_commercial_products():
    key = business_key(
        "commercial_products",
        {
            "reference": " A0602.0100 ",
            "brand": "Duchefa",
            "name": "Agar",
            "sold_packaging_label": "100 g",
        },
    )

    assert key == "reference:a0602.0100"


def test_same_id_draft_on_both_sides_is_non_validated_conflict():
    ref = {
        "commercial_products": {
            "p1": {
                "id": "p1",
                "name": "A",
                "reference": "R1",
                "code_nacres": "NA25",
                "status": "draft",
            }
        }
    }
    data = {
        "id": "p1",
        "name": "B",
        "reference": "R1",
        "code_nacres": "NA25",
        "status": "pending",
    }

    result = classify_row("commercial_products", data, ref)

    assert result.kind == "NON_VALIDE_DES_DEUX_COTES"


def test_same_business_key_against_validated_is_revision_possible():
    ref = {
        "commercial_products": {
            "p1": {
                "id": "p1",
                "name": "Produit validé",
                "reference": "R1",
                "code_nacres": "NA25",
                "status": "validated",
            }
        }
    }
    data = {
        "id": "p2",
        "name": "Produit modifié",
        "reference": "R1",
        "code_nacres": "NA25",
        "status": "draft",
    }

    result = classify_row("commercial_products", data, ref)

    assert result.kind == "REVISION_POSSIBLE"
    assert result.existing["id"] == "p1"


def test_new_entry_is_importable_new():
    ref = {"emission_factors": {}}
    data = {
        "id": "ef1",
        "name": "Facteur",
        "name_key": "facteur",
        "factor_type": "solid",
        "status": "draft",
    }

    result = classify_row("emission_factors", data, ref)

    assert result.kind == "NOUVEAU"

