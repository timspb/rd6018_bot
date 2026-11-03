"""The existing battery START preview offers saved dynamic recipe copies."""
import tempfile
import types
import unittest
from pathlib import Path

from production_bot_ui import _recipe_preview_keyboard
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary


class NativeTelegramSelectionButtonTests(unittest.TestCase):
    def test_saved_copy_appears_in_existing_start_preview(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = RecipeCatalog(RecipeLibrary(
                Path(root) / "user_recipes", max_voltage_v=15.5,
                max_current_a=7.2,
            ))
            drafts = NativeRecipeDraftLibrary(Path(root) / "native_recipe_drafts")
            drafts.save("my_efb", 1, {
                "schema": 1, "execution_kind": "native_authority",
                "base_recipe_id": "native_efb_normal", "overrides": {},
            })
            app = types.SimpleNamespace(_user_recipe_catalog=catalog)
            rows = _recipe_preview_keyboard(app, "v2_battery_start").inline_keyboard
            callbacks = [button.callback_data for row in rows for button in row]
            self.assertIn("v2_native_pick:my_efb:1", callbacks)
            self.assertIn("v2_battery_start", callbacks)
            self.assertTrue(all(len(callback.encode("utf-8")) <= 64
                                for callback in callbacks))

    def test_unconfigured_native_library_keeps_original_preview(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = RecipeCatalog(RecipeLibrary(
                Path(root) / "user_recipes", max_voltage_v=15.5,
                max_current_a=7.2,
            ))
            app = types.SimpleNamespace(_user_recipe_catalog=catalog)
            rows = _recipe_preview_keyboard(app, "v2_battery_start").inline_keyboard
            callbacks = [button.callback_data for row in rows for button in row]
            self.assertIn("v2_battery_start", callbacks)
            self.assertFalse(any(x.startswith("v2_native_pick:") for x in callbacks))
