"""Empty-library route must actually create a draft, never start Output."""
import tempfile
import types
import unittest

from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary
from production_bot_ui import _recipe_preview_keyboard


class EmptyRecipePreviewEntryTests(unittest.TestCase):
    def test_create_button_routes_to_non_energizing_draft_handler(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = RecipeCatalog(RecipeLibrary(root, max_voltage_v=15.5, max_current_a=7.2))
            app = types.SimpleNamespace(_user_recipe_catalog=catalog)
            buttons = _recipe_preview_keyboard(app, "v2_battery_start")
            callbacks = [item.callback_data for row in buttons.inline_keyboard for item in row]
            self.assertIn("recipes:create", callbacks)
            self.assertIn("v2_battery_start", callbacks)
            self.assertNotIn("recipes:list", callbacks)
            self.assertEqual(catalog.list_recipes(), ())
