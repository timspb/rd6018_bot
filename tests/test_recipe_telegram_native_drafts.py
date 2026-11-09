"""RS-3B: native preset copy and native draft browsing share Telegram owner."""
from __future__ import annotations

import tempfile
import unittest

from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.ui.telegram.recipes import install_recipe_catalog_commands
from runtime.ui.telegram.recipe_buttons import native_recipe_markup
from test_recipe_real_callback_chain import _App, _Call


def buttons(response):
    return [b.callback_data for row in response.inline_keyboard for b in row]


class NativeDraftBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_copy_native_view_and_history(self):
        with tempfile.TemporaryDirectory() as path:
            catalog = RecipeCatalog(RecipeLibrary(path + "/recipes",
                                    max_voltage_v=15.5, max_current_a=7.2))
            drafts = NativeRecipeDraftLibrary(path + "/native_recipe_drafts")
            app = _App()
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = {h.callback.__name__: h.callback
                        for h in app.router.callback_query.handlers}
            self.assertIn("recipes:nd:list", buttons(native_recipe_markup()))
            first = _Call("recipes:nd:copy:native_efb_normal")
            await handlers["native_draft_copy"](first)
            self.assertEqual(len(first.acks), 1)
            self.assertEqual(len(first.message.sent), 1)
            copy_buttons = buttons(first.message.sent[0][1]["reply_markup"])
            self.assertEqual(len(copy_buttons), 2)
            self.assertIn("recipes:nd:list", copy_buttons)
            self.assertTrue(all(len(data.encode("utf-8")) <= 64 for data in copy_buttons))
            names = drafts.list_drafts()
            self.assertEqual(len(names), 1)
            name = names[0]
            self.assertEqual(drafts.load(name, 1).base_recipe_id, "native_efb_normal")
            items = _Call("recipes:nd:list")
            await handlers["native_draft_list"](items)
            callback = f"recipes:nd:view:{name}:1"
            self.assertIn(callback, copy_buttons)
            self.assertIn(callback, buttons(items.message.sent[0][1]["reply_markup"]))
            selected = _Call(callback)
            await handlers["native_draft_view"](selected)
            self.assertIn("native_efb_normal", selected.message.sent[0][0])
            self.assertIn("не запускает зарядку", selected.message.sent[0][0])
            self.assertEqual(catalog.list_recipes(), ())

    async def test_unapproved_chat_cannot_copy(self):
        class Denied(_App):
            async def _check_chat_and_respond(self, call):
                return False
        with tempfile.TemporaryDirectory() as path:
            catalog = RecipeCatalog(RecipeLibrary(path + "/recipes",
                                   max_voltage_v=15.5, max_current_a=7.2))
            app = Denied()
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = {h.callback.__name__:h.callback
                        for h in app.router.callback_query.handlers}
            call = _Call("recipes:nd:copy:native_efb_normal")
            await handlers["native_draft_copy"](call)
            self.assertFalse(call.message.sent)
            drafts = NativeRecipeDraftLibrary(path + "/native_recipe_drafts")
            self.assertEqual(drafts.list_drafts(), ())

    async def test_invalid_native_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as path:
            catalog = RecipeCatalog(RecipeLibrary(path + "/recipes",
                                   max_voltage_v=15.5, max_current_a=7.2))
            app = _App()
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = {h.callback.__name__:h.callback
                        for h in app.router.callback_query.handlers}
            call = _Call("recipes:nd:copy:native_nonexistent")
            await handlers["native_draft_copy"](call)
            self.assertFalse(call.message.sent)
            self.assertTrue(call.acks[0][1]["show_alert"])
