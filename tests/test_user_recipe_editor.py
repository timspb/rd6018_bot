import tempfile
import unittest
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_editor import edit_step


class EditorTests(unittest.TestCase):
    def test_editor_creates_revision_and_rejects_stale_or_unsafe(self):
        with tempfile.TemporaryDirectory() as root:
            library = RecipeLibrary(root, max_voltage_v=15.5, max_current_a=7.2)
            catalog = RecipeCatalog(library)
            library.save({"id": "trial", "version": 1, "steps": [
                {"action": "set", "params": {"voltage_v": 14.7, "current_a": 1.0},
                 "until": {"after_seconds": 20}},
            ]})
            edited = edit_step(catalog, "trial", 1, 0, field="voltage_v", value=14.8)
            self.assertEqual(edited.version, 2)
            self.assertEqual(library.load("trial", 1).steps[0]["params"]["voltage_v"], 14.7)
            with self.assertRaises(ValueError):
                edit_step(catalog, "trial", 1, 0, field="voltage_v", value=14.9)
            with self.assertRaises(ValueError):
                edit_step(catalog, "trial", 2, 0, field="voltage_v", value=18.0)
            self.assertEqual(library.versions("trial"), (1, 2))
