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
                            "conditionnement": "1x500",
                            "origine": "Europe",
                        }
                    ],
                    source=ManipsTypeDB.SOURCE_USER,
                )

                items = db.get_manip_items("Manip provenance")

                self.assertEqual(len(items), 1)
                self.assertEqual(items[0]["origine"], "Europe")
                self.assertEqual(items[0]["conditionnement"], "1x500")
            finally:
                db.close()


class TestManipsTypeDBInit(unittest.TestCase):
    def test_absolute_path_used_as_is(self):
        """Un chemin absolu passé au constructeur ne doit pas être réencapsulé par resource_path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            abs_path = os.path.join(tmpdir, "test.sqlite")
            db = ManipsTypeDB(db_path=abs_path)
            try:
                self.assertEqual(db.db_path, abs_path)
            finally:
                db.close()

    def test_normalize_source_user_legacy(self):
        """SOURCE_USER_LEGACY doit être normalisé vers SOURCE_USER."""
        self.assertEqual(
            ManipsTypeDB.normalize_source(ManipsTypeDB.SOURCE_USER_LEGACY),
            ManipsTypeDB.SOURCE_USER,
        )

    def test_source_filter_values_user_includes_legacy(self):
        """Le filtre SOURCE_USER doit inclure la valeur legacy pour la rétrocompatibilité."""
        values = ManipsTypeDB.source_filter_values(ManipsTypeDB.SOURCE_USER)
        self.assertIn(ManipsTypeDB.SOURCE_USER, values)
        self.assertIn(ManipsTypeDB.SOURCE_USER_LEGACY, values)


if __name__ == "__main__":
    unittest.main()
