import tempfile
import unittest
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.recipe_schema import parse_recipe


def doc(version=1, voltage=14.7):
    return {"id": "trial", "version": version, "steps": [
        {"action": "set", "params": {"voltage_v": voltage, "current_a": 2.0},
         "until": {"voltage_gte": 13.12}},
        {"action": "off", "params": {}, "until": {"after_seconds": 10}},
        {"action": "wait", "params": {}, "until": {"voltage_lte": 12.0}},
    ]}


class UserRecipeLibraryTests(unittest.TestCase):
    def test_versioned_immutable_save_and_load(self):
        with tempfile.TemporaryDirectory() as folder:
            library = RecipeLibrary(folder, max_voltage_v=15.5, max_current_a=7.2)
            first = library.save(doc())
            self.assertEqual(library.load("trial", 1).digest, first.digest)
            with self.assertRaises(FileExistsError):
                library.save(doc(voltage=14.8))
            second = library.save(doc(version=2, voltage=14.8))
            self.assertNotEqual(first.digest, second.digest)
            self.assertEqual(library.versions("trial"), (1, 2))

    def test_hardware_limit_rejected(self):
        with self.assertRaises(ValueError):
            parse_recipe(doc(voltage=18.0), max_voltage_v=15.5, max_current_a=7.2)

    def test_unknown_action_and_invalid_numbers_rejected(self):
        bad = doc()
        bad["steps"][0]["action"] = "python"
        with self.assertRaises(ValueError):
            parse_recipe(bad, max_voltage_v=15.5, max_current_a=7.2)
        bad = doc()
        bad["steps"][0]["params"]["current_a"] = float("nan")
        with self.assertRaises(ValueError):
            parse_recipe(bad, max_voltage_v=15.5, max_current_a=7.2)
