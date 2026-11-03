"""Telegram native recipe clone/edit/show is durable and never applies a draft."""
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.ui.telegram.recipes import install_recipe_catalog_commands
from test_recipe_real_callback_chain import _App, _Message


class _NativeMessage(_Message):
    def __init__(self, text):
        super().__init__()
        self.text = text


class NativeTelegramDraftCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_copy_edit_view_versions_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = RecipeCatalog(RecipeLibrary(Path(root) / "user_recipes",
                                                  max_voltage_v=15.5, max_current_a=7.2))
            app = _App()
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = {h.callback.__name__: h.callback
                        for h in app.router.message.handlers}
            store = NativeRecipeDraftLibrary(Path(root) / "native_recipe_drafts")
            copy = _NativeMessage("/native_copy native_efb_normal my_efb")
            await handlers["_native_copy"](copy)
            self.assertEqual(store.versions("my_efb"), (1,))
            self.assertIn("не активируется", copy.sent[0][0])
            change = _NativeMessage("/native_set my_efb charge.main.efb_voltage_v 14.6")
            await handlers["_native_set"](change)
            self.assertEqual(store.versions("my_efb"), (1, 2))
            self.assertEqual(dict(store.load("my_efb", 2).overrides),
                             {"charge.main.efb_voltage_v": 14.6})
            show = _NativeMessage("/native_show my_efb")
            await handlers["_native_show"](show)
            self.assertIn("14.6", show.sent[0][0])
            self.assertIn("не применяется", show.sent[0][0])
            bad = _NativeMessage("/native_set my_efb charge.main.efb_voltage_v 50")
            await handlers["_native_set"](bad)
            self.assertIn("Ошибка", bad.sent[0][0])
            self.assertEqual(store.versions("my_efb"), (1, 2))
            duplicate = _NativeMessage("/native_copy native_agm_normal my_efb")
            await handlers["_native_copy"](duplicate)
            self.assertIn("Ошибка", duplicate.sent[0][0])
            self.assertEqual(store.load("my_efb", 1).base_recipe_id,
                             "native_efb_normal")
            self.assertEqual(catalog.list_recipes(), ())

    async def test_unknown_source_never_writes(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = RecipeCatalog(RecipeLibrary(Path(root) / "user_recipes",
                                                  max_voltage_v=15.5, max_current_a=7.2))
            app = _App()
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = {h.callback.__name__: h.callback
                        for h in app.router.message.handlers}
            call = _NativeMessage("/native_copy fake unknown")
            await handlers["_native_copy"](call)
            self.assertIn("Ошибка", call.sent[0][0])
            self.assertFalse((Path(root) / "native_recipe_drafts").exists())

