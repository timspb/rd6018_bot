"""Fake-only tests for START's pure recipe selection boundary."""
import tempfile
import types
import unittest
from pathlib import Path

from application.start_recipe_selection import (
    resolve_native_recipe_copy,
    resolve_user_step_recipe,
)
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary


class StartRecipeSelectionTests(unittest.TestCase):
    def _app(self, root):
        library = RecipeLibrary(Path(root) / "recipes", max_voltage_v=15.5,
                                max_current_a=7.2)
        return types.SimpleNamespace(_user_recipe_catalog=RecipeCatalog(library))

    @staticmethod
    def _pending(**values):
        return types.SimpleNamespace(profile="EFB", intent="recovery", **values)

    def test_valid_user_recipe_is_returned_as_loaded_with_no_native_selection(self):
        with tempfile.TemporaryDirectory() as root:
            app = self._app(root)
            app._user_recipe_catalog.library.save({
                "id": "first_set", "version": 1,
                "steps": [{"action": "set",
                           "params": {"voltage_v": 14.4, "current_a": 2.0},
                           "until": {"after_seconds": 60}}],
            })
            pending = self._pending(recipe_id="first_set", recipe_version=1)
            recipe = resolve_user_step_recipe(app, pending)
            native = resolve_native_recipe_copy(app, pending, recipe)
            self.assertEqual(recipe.recipe_id, "first_set")
            self.assertIsNone(native)

    def test_user_recipe_without_first_set_is_rejected_before_start(self):
        with tempfile.TemporaryDirectory() as root:
            app = self._app(root)
            app._user_recipe_catalog.library.save({
                "id": "off_first", "version": 1,
                "steps": [{"action": "off", "params": {},
                           "until": {"after_seconds": 60}}],
            })
            with self.assertRaisesRegex(ValueError, "первый шаг.*SET"):
                resolve_user_step_recipe(
                    app, self._pending(recipe_id="off_first", recipe_version=1))

    def test_native_and_user_recipe_selections_remain_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as root:
            app = self._app(root)
            app._user_recipe_catalog.library.save({
                "id": "first_set", "version": 1,
                "steps": [{"action": "set",
                           "params": {"voltage_v": 14.4, "current_a": 2.0},
                           "until": {"after_seconds": 60}}],
            })
            pending = self._pending(recipe_id="first_set", recipe_version=1,
                                    native_recipe_name="copy",
                                    native_recipe_version=1)
            with self.assertRaisesRegex(ValueError, "mutually exclusive"):
                recipe = resolve_user_step_recipe(app, pending)
                resolve_native_recipe_copy(app, pending, recipe)


if __name__ == "__main__":
    unittest.main()
