from a_manips_type_db import ManipsTypeDB

db = ManipsTypeDB('manips_types/manips_type.sqlite')

# Je veux ajouter une manip "native" :
db.add_manip(
    "Manip A", 
    [
        {
            "category": "Machine",
            "subcategory": "Microscope",
            "subsubcategory": "KC21 - Litiere",
            "name": "Microscope 3000",
            "value": 5.0,
            "unit": "kWh"
        },
        {
            "category": "Achats",
            "subcategory": "Pipettes",
            "subsubcategory": "LA11 - Vaccins",
            "name": "Pipettes stériles",
            "value": 10.0,
            "unit": "€"
        }
    ],
    source="native"
)

manip_names = db.list_manips()
print(manip_names)