import tempfile
import unittest
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.recipe_editor import transform_steps


class TransformTests(unittest.TestCase):
    def test_move_condition_delete_keep_earlier_versions(self):
        with tempfile.TemporaryDirectory() as root:
            lib = RecipeLibrary(root, max_voltage_v=15.5, max_current_a=7.2)
            cat = RecipeCatalog(lib)
            lib.save({"id": "test", "version": 1, "steps": [
                {"action": "set", "params": {"voltage_v": 14.7, "current_a": 1},
                 "until": {"after_seconds": 5}},
                {"action": "off", "params": {}, "until": {"after_seconds": 2}},
            ]})
            v2 = transform_steps(cat, "test", 1, "move", 1, destination=0)
            self.assertEqual(v2.steps[0]["action"], "off")
            v3 = transform_steps(cat, "test", 2, "condition", 1,
                                 condition="voltage_gte", threshold=13.12)
            self.assertEqual(v3.steps[1]["until"], {"voltage_gte": 13.12})
            v4 = transform_steps(cat, "test", 3, "delete", 0)
            self.assertEqual(len(v4.steps), 1)
            self.assertEqual(len(lib.load("test", 1).steps), 2)
            with self.assertRaises(ValueError):
                transform_steps(cat, "test", 4, "delete", 0)
            with self.assertRaises(ValueError):
                transform_steps(cat, "test", 3, "move", 0, destination=0)
