"""RS-3A: button-only Telegram history/copy/archive via existing catalog."""
from __future__ import annotations

import tempfile
import unittest

from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.ui.telegram.recipe_buttons import recipe_history_markup, recipe_markup
from runtime.ui.telegram.recipes import install_recipe_catalog_commands
from test_recipe_real_callback_chain import _App, _Call


STEP = [{"action": "off", "params": {}, "until": {"after_seconds": 10}}]


def button_data(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


class TelegramRecipeHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_copy_and_confirm_archive_keep_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = RecipeCatalog(RecipeLibrary(folder, max_voltage_v=15.5, max_current_a=7.2))
            original = catalog.library.save({"id": "project", "version": 1, "steps": STEP})
            second = catalog.next_version("project", [
                {"action": "off", "params": {}, "until": {"after_seconds": 20}},
            ])
            before = (catalog.library.root / "project" / "v1.json").read_bytes()
            self.assertEqual(second.version, 2)
            app = _App()
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = {h.callback.__name__: h.callback
                        for h in app.router.callback_query.handlers}
            toolbar = button_data(recipe_markup("project", 2))
            self.assertIn("recipes:history:project:0", toolbar)
            self.assertIn("recipes:duplicate:project:2", toolbar)
            self.assertIn("recipes:archiveask:project", toolbar)
            self.assertTrue(all(len(x.encode()) <= 64 for x in toolbar))

            hist = _Call("recipes:history:project:0")
            await handlers["recipe_history"](hist)
            self.assertIn("История: project", hist.message.sent[0][0])
            versions = button_data(hist.message.sent[0][1]["reply_markup"])
            self.assertIn("recipes:view:project:2", versions)
            self.assertIn("recipes:view:project:1", versions)

            dupe = _Call("recipes:duplicate:project:2")
            await handlers["recipe_duplicate"](dupe)
            self.assertEqual(len(dupe.acks), 1)
            copies = [n for n in catalog.list_recipes() if n.startswith("copy_")]
            self.assertEqual(len(copies), 1)
            self.assertEqual(catalog.library.load(copies[0], 1).steps, second.steps)

            ask = _Call("recipes:archiveask:project")
            await handlers["recipe_archive_ask"](ask)
            self.assertEqual(len(ask.acks), 1)
            confirm_buttons = button_data(ask.message.sent[0][1]["reply_markup"])
            self.assertIn("recipes:archiveconfirm:project", confirm_buttons)
            self.assertIn("recipes:list", confirm_buttons)
            self.assertIn("project", catalog.active_recipes())

            yes = _Call("recipes:archiveconfirm:project")
            await handlers["recipe_archive_confirm"](yes)
            self.assertEqual(len(yes.acks), 1)
            self.assertNotIn("project", catalog.active_recipes())
            self.assertEqual((catalog.library.root / "project" / "v1.json").read_bytes(), before)
            self.assertEqual(catalog.library.versions("project"), (1, 2))
            with self.assertRaisesRegex(ValueError, "archived"):
                catalog.next_version("project", STEP)
            self.assertIn(copies[0], catalog.active_recipes())

    async def test_history_pagination_and_missing_source_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = RecipeCatalog(RecipeLibrary(folder, max_voltage_v=15.5, max_current_a=7.2))
            for v in range(1, 19):
                catalog.library.save({"id": "long_history", "version": v,
                                      "steps": [{"action":"off","params":{},
                                                 "until":{"after_seconds":v}}]})
            first = button_data(recipe_history_markup(catalog, "long_history", page=0))
            second = button_data(recipe_history_markup(catalog, "long_history", page=1))
            last = button_data(recipe_history_markup(catalog, "long_history", page=2))
            self.assertIn("recipes:view:long_history:18", first)
            self.assertIn("recipes:history:long_history:1", first)
            self.assertIn("recipes:view:long_history:10", second)
            self.assertIn("recipes:view:long_history:2", last)
            self.assertTrue(all(len(s.encode()) <= 64 for s in first + second + last))
            with self.assertRaises(ValueError):
                recipe_history_markup(catalog, "long_history", page=3)

            app = _App()
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = {h.callback.__name__: h.callback
                        for h in app.router.callback_query.handlers}
            missing = _Call("recipes:duplicate:missing:1")
            await handlers["recipe_duplicate"](missing)
            self.assertEqual(missing.message.sent, [])
            self.assertTrue(missing.acks[0][1]["show_alert"])

    async def test_long_ids_never_emit_oversized_telegram_callback(self):
        name = "x" * 80
        toolbar = button_data(recipe_markup(name, 123))
        self.assertIn("recipes:list", toolbar)
        self.assertTrue(all(len(item.encode("utf-8")) <= 64 for item in toolbar))

    async def test_unapproved_chat_cannot_mutate(self):
        class Denied(_App):
            async def _check_chat_and_respond(self, call):
                return False
        with tempfile.TemporaryDirectory() as folder:
            catalog = RecipeCatalog(RecipeLibrary(folder, max_voltage_v=15.5, max_current_a=7.2))
            catalog.library.save({"id": "mytest", "version":1, "steps":STEP})
            app = Denied()
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = {h.callback.__name__:h.callback
                        for h in app.router.callback_query.handlers}
            for name, data in (
                ("recipe_duplicate","recipes:duplicate:mytest:1"),
                ("recipe_archive_confirm","recipes:archiveconfirm:mytest"),
            ):
                call = _Call(data)
                await handlers[name](call)
                self.assertFalse(call.message.sent)
            self.assertEqual(catalog.active_recipes(), ("mytest",))
