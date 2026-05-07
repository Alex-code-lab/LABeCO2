import os
import tempfile
import unittest

from scenarios.manip_type_db import ManipsTypeDB


class TestManipsTypeDB(unittest.TestCase):
    def test_origine_is_persisted_for_manip_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = ManipsTypeDB(os.path.join(tmpdir, "manips.sqlite"))
            try:
                db.add_manip(
                    "Manip provenance",
                    [
                        {
                            "category": "Achats",
                            "subcategory": "Consommables",
                            "subsubcategory": "NB11",
                            "code_nacres": "NB11",
                            "name": "MICROTUBES",
                            "value": 10.0,
                            "unit": "euro",
                            "days": 1,
                            "quantity": 2.0,
                            "consommable": "Tube centrifugeuse 15 mL",
                            "origine": "Europe",
                        }
                    ],
                    source=ManipsTypeDB.SOURCE_USER,
                )

                items = db.get_manip_items("Manip provenance")

                self.assertEqual(len(items), 1)
                self.assertEqual(items[0]["origine"], "Europe")
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
