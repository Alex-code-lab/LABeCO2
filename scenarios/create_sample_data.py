# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024, LABeCO2, Alexandre Souchaud. Tous droits réservés.
#
# Ce fichier fait partie du projet LABeCO2.
# Distribué sous licence : GNU GPL v3 (non commercial)
# scenarios/create_sample_data.py
from manip_type_db import ManipsTypeDB

db = ManipsTypeDB('scenarios/manips_type.sqlite')

NATIVE_MANIPS = [
    # {
    #     "name": "Manip A",
    #     "items": [
    #         {
    #             "category": "Machine",
    #             "subcategory": "Microscope",
    #             "subsubcategory": "KC21 - Litiere",
    #             "name": "Microscope 3000",
    #             "value": 5.0,
    #             "unit": "kWh"
    #         },
    #         {
    #             "category": "Achats",
    #             "subcategory": "Pipettes",
    #             "subsubcategory": "LA11 - Vaccins",
    #             "name": "Pipettes stériles",
    #             "value": 10.0,
    #             "unit": "€",
    #             "quantity": 100.0
    #         }
    #     ]
    # },
]

for manip in NATIVE_MANIPS:
    db.add_manip(
        manip["name"],
        manip["items"],
        source=ManipsTypeDB.SOURCE_NATIVE
    )

manip_names = db.list_manips()
print(manip_names)
