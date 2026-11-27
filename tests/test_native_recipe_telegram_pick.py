"""The existing battery START preview offers saved dynamic recipe copies."""
import tempfile
import types
import unittest
from pathlib import Path

from production_bot_ui import _recipe_preview_keyboard
import production_bot_ui
from runtime.ui.telegram.recipe_buttons import (
    _preview_keyboard as owner_preview_keyboard,
    _recipe_preview_keyboard as owner_recipe_preview_keyboard,
)
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary


class NativeTelegramSelectionButtonTests(unittest.TestCase):
    def test_production_ui_exports_the_recipe_keyboard_owner_functions(self):
        # Other legacy UI tests replace the preview global at runtime; test
        # the declared compatibility import independently of that patch state.
        import ast
        source = Path(production_bot_ui.__file__).read_text(encoding="utf-8")
        imports = [
            alias.name for node in ast.parse(source).body
            if isinstance(node, ast.ImportFrom)
            and node.module == "runtime.ui.telegram.recipe_buttons"
            for alias in node.names
        ]
        self.assertIn("_preview_keyboard", imports)
        self.assertIn("_recipe_preview_keyboard", imports)
        self.assertIs(_recipe_preview_keyboard, owner_recipe_preview_keyboard)

    def test_missing_catalog_keeps_original_rows_and_order(self):
        markup = _recipe_preview_keyboard(types.SimpleNamespace(), "v2_battery_start")
        self.assertEqual(
            [[button.callback_data for button in row] for row in markup.inline_keyboard],
            [["v2_battery_start"], ["ui:nav.charge"]],
        )

    def test_active_recipe_is_selectable_and_archived_recipe_stays_hidden(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = RecipeCatalog(RecipeLibrary(
                Path(root) / "user_recipes", max_voltage_v=15.5,
                max_current_a=7.2,
            ))
            recipe = {"steps": [{"action": "wait", "params": {},
                                "until": {"after_seconds": 10}}]}
            catalog.library.save({"id": "active", "version": 1, **recipe})
            catalog.library.save({"id": "archived", "version": 1, **recipe})
            catalog.archive("archived")
            app = types.SimpleNamespace(_user_recipe_catalog=catalog)
            callbacks = [button.callback_data for row in
                         _recipe_preview_keyboard(app, "v2_battery_start").inline_keyboard
                         for button in row]
            self.assertIn("v2_recipe_pick:active:1", callbacks)
            self.assertNotIn("v2_recipe_pick:archived:1", callbacks)

    def test_catalog_exception_is_not_silently_swallowed(self):
        class Catalog:
            library = types.SimpleNamespace(root=Path("/tmp/unused"))

            @staticmethod
            def active_recipes():
                raise RuntimeError("catalog unavailable")

        with self.assertRaisesRegex(RuntimeError, "catalog unavailable"):
            _recipe_preview_keyboard(
                types.SimpleNamespace(_user_recipe_catalog=Catalog()),
                "v2_battery_start",
            )

    def test_preview_preserves_order_caps_and_omits_unselectable_callbacks(self):
        with tempfile.TemporaryDirectory() as root:
            class Library:
                @staticmethod
                def versions(name):
                    return (1, 2)

            Library.root = Path(root) / "user_recipes"

            class Catalog:
                library = Library()

                @staticmethod
                def active_recipes():
                    # Archived names are absent from active_recipes by contract.
                    return tuple([f"r{i:02d}" for i in range(27)] + ["x" * 60])

            drafts = NativeRecipeDraftLibrary(Path(root) / "native_recipe_drafts")
            drafts.save("native", 1, {
                "schema": 1, "execution_kind": "native_authority",
                "base_recipe_id": "native_efb_normal", "overrides": {},
            })
            app = types.SimpleNamespace(_user_recipe_catalog=Catalog())
            rows = _recipe_preview_keyboard(app, "v2_battery_start").inline_keyboard
            callbacks = [button.callback_data for row in rows for button in row]
            # Historical layout retains START first, inserts up to 24
            # recipe choices after it, and keeps navigation last.
            self.assertEqual(callbacks[0], "v2_battery_start")
            self.assertEqual(callbacks[1:4], [
                "v2_recipe_pick:r00:2", "v2_recipe_pick:r01:2",
                "v2_recipe_pick:r02:2",
            ])
            self.assertEqual(callbacks[24], "v2_recipe_pick:r23:2")
            self.assertEqual(callbacks[25], "ui:nav.charge")
            self.assertEqual(len(callbacks), 26)
            self.assertNotIn("v2_recipe_pick:r24:2", callbacks)
            self.assertNotIn("v2_recipe_pick:" + "x" * 60 + ":2", callbacks)
            self.assertTrue(all(len(item.encode("utf-8")) <= 64 for item in callbacks))

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
