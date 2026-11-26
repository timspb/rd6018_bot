import tempfile
import unittest
from unittest.mock import Mock

from application.start_recipe_selection import select_user_recipe_for_start
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary


class StartRecipeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.catalog = RecipeCatalog(RecipeLibrary(
            self.directory.name, max_voltage_v=18.0, max_current_a=20.0,
        ))

    def test_selects_immutable_first_set_recipe_without_runner_or_mutation(self):
        self.catalog.library.save({"id": "chosen", "version": 1, "steps": [
            {"action": "set", "params": {"voltage_v": 13.8, "current_a": 1.2},
             "until": {"after_seconds": 30}},
            {"action": "off", "params": {}, "until": {"after_seconds": 1}},
        ]})
        load = Mock(wraps=self.catalog.library.load)
        self.catalog.library.load = load

        first = select_user_recipe_for_start(
            catalog=self.catalog, recipe_id="chosen", version=1,
        )
        second = select_user_recipe_for_start(
            catalog=self.catalog, recipe_id="chosen", version=1,
        )

        self.assertEqual(first, second)
        self.assertEqual(load.call_args_list, [
            unittest.mock.call("chosen", 1), unittest.mock.call("chosen", 1),
        ])
        self.assertEqual(first.steps[0]["action"], "set")
        self.assertFalse((self.catalog.library.root / "_runs").exists())

    def test_rejects_off_first_selection_before_runner_creation(self):
        self.catalog.library.save({"id": "off-first", "version": 1, "steps": [
            {"action": "off", "params": {}, "until": {"after_seconds": 1}},
            {"action": "wait", "params": {}, "until": {"after_seconds": 2}},
        ]})

        with self.assertRaisesRegex(ValueError, "первый шаг.*SET"):
            select_user_recipe_for_start(
                catalog=self.catalog, recipe_id="off-first", version=1,
            )
        self.assertFalse((self.catalog.library.root / "_runs").exists())

    def test_rejects_malformed_recipe_structure(self):
        self.catalog.library.save({"id": "bad-flow", "version": 1, "steps": [
            {"action": "set", "params": {"voltage_v": 13.8, "current_a": 1.2},
             "until": {"after_seconds": 30}},
            {"action": "wait", "params": {}, "until": {"after_seconds": 2}},
        ]})

        with self.assertRaisesRegex(ValueError, "WAIT must immediately follow OFF"):
            select_user_recipe_for_start(
                catalog=self.catalog, recipe_id="bad-flow", version=1,
            )


if __name__ == "__main__":
    unittest.main()
