import tempfile
import unittest

from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.recipe_catalog import RecipeCatalog


def document(name, version=1):
    return {"id": name, "version": version, "steps": [
        {"action": "set", "params": {"voltage_v": 14.7, "current_a": 2},
         "until": {"after_seconds": 10}},
        {"action": "off", "params": {}, "until": {"after_seconds": 2}},
    ]}


class CatalogTests(unittest.TestCase):
    def test_immutable_versions_copy_and_archive(self):
        with tempfile.TemporaryDirectory() as root:
            lib = RecipeLibrary(root, max_voltage_v=15.5, max_current_a=7.2)
            catalog = RecipeCatalog(lib)
            self.assertEqual(catalog.list_recipes(), ())
            original = lib.save(document("original"))
            copy = catalog.duplicate("original", 1, "copy")
            self.assertNotEqual(copy.digest, original.digest)
            self.assertEqual(lib.versions("copy"), (1,))
            new = catalog.next_version("original", document("original")["steps"])
            self.assertEqual(new.version, 2)
            self.assertEqual(catalog.active_recipes(), ("copy", "original"))
            catalog.archive("original")
            self.assertEqual(catalog.active_recipes(), ("copy",))
            self.assertEqual(lib.versions("original"), (1, 2))
            with self.assertRaises(FileExistsError):
                catalog.archive("original")
