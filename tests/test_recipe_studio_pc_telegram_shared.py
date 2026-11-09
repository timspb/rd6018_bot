"""PC local bridge and Telegram callbacks on the same explicit scratch libraries.

No node104, hardware connection, cloud copy, or production Telegram.
"""
from __future__ import annotations

from copy import deepcopy
import unittest

from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.ui.telegram.recipes import install_recipe_catalog_commands
from test_recipe_real_callback_chain import _App, _Call
from test_recipe_studio_local_bridge import TestStudioBridge, STEP, NATIVE


def button_data(call):
    return [button.callback_data
            for _, kwargs in call.message.sent
            for row in kwargs.get("reply_markup").inline_keyboard
            for button in row]


class SharedLibraryPCAndTelegramTests(TestStudioBridge):
    """Use the real authenticated localhost HTTP API and real Telegram callbacks."""

    def setUp(self):
        super().setUp()
        self.catalog = RecipeCatalog(self.server.store("step"))
        self.native_drafts = self.server.store("native")
        self.app = _App()
        install_recipe_catalog_commands(self.app, catalog=self.catalog,
                                        native_drafts=self.native_drafts)
        self.callbacks = {handler.callback.__name__: handler.callback
                          for handler in self.app.router.callback_query.handlers}

    def call(self, handler_name, data):
        call = _Call(data)
        import asyncio
        asyncio.run(self.callbacks[handler_name](call))
        return call

    def test_pc_step_save_telegram_history_and_archive_are_same_files(self):
        status, saved = self.request("POST", "/api/save",
                                     {"kind": "step", "recipe": STEP})
        self.assertEqual(status, 200, saved)
        first = self.server.store("step").load("test_step", 1)
        view = self.call("show_recipe", "recipes:view:test_step:1")
        self.assertIn("test_step", view.message.sent[0][0])
        revised = deepcopy(STEP)
        revised["version"] = 2
        revised["steps"][0]["params"]["voltage_v"] = 14.8
        self.assertEqual(self.request("POST", "/api/save",
                         {"kind": "step", "recipe": revised})[0], 200)
        history = self.call("recipe_history", "recipes:history:test_step:0")
        self.assertIn("recipes:view:test_step:2", button_data(history))
        self.assertEqual(self.server.store("step").load("test_step", 1), first)
        self.assertEqual(self.server.store("step").versions("test_step"), (1, 2))
        status, _ = self.request("POST", "/api/archive",
                                 {"kind": "step", "id": "test_step"})
        self.assertEqual(status, 200)
        listing = self.request("POST", "/api/list", {"kind": "step"})[1]
        self.assertTrue(listing["items"][0]["archived"])
        old = self.call("show_recipe", "recipes:view:test_step:1")
        self.assertTrue(old.message.sent)
        self.assertEqual(self.request("POST", "/api/save",
                         {"kind": "step", "recipe": dict(STEP, version=3)})[0], 422)

    def test_pc_native_save_telegram_button_edit_pc_reload_stale(self):
        status, saved = self.request("POST", "/api/save",
                                     {"kind": "native", "recipe": NATIVE})
        self.assertEqual(status, 200, saved)
        list_call = self.call("native_draft_list", "recipes:nd:list")
        self.assertIn("recipes:nd:view:test_native:1", button_data(list_call))
        view = self.call("native_draft_view", "recipes:nd:view:test_native:1")
        self.assertIn("recipes:nd:edit:test_native:1:0", button_data(view))
        edit = self.call("native_draft_edit", "recipes:nd:edit:test_native:1:0")
        adjust = next(data for data in button_data(edit)
                      if data.startswith("recipes:nd:adjust:") and data.endswith(":up"))
        self.assertTrue(all(len(data.encode("utf-8")) <= 64
                            for data in button_data(edit)))
        result = self.call("native_draft_adjust", adjust)
        self.assertEqual(len(result.acks), 1)
        self.assertEqual(self.native_drafts.versions("test_native"), (1, 2))
        status, loaded = self.request("POST", "/api/load",
                                      {"kind": "native", "id": "test_native", "version": 2})
        self.assertEqual(status, 200, loaded)
        self.assertTrue(loaded["recipe"]["draft"]["overrides"])
        self.assertEqual(loaded["recipe"]["version"], 2)
        self.assertFalse(loaded["physical_start_authorized"])
        self.assertEqual(self.native_drafts.load("test_native", 1).overrides, ())
        stale = self.request("POST", "/api/save",
                             {"kind": "native", "recipe": dict(NATIVE, version=2)})
        self.assertEqual(stale[0], 422)
        status, _ = self.request("POST", "/api/archive",
                                 {"kind": "native", "id": "test_native"})
        self.assertEqual(status, 200)
        blocked = self.call("native_draft_edit", "recipes:nd:edit:test_native:2:0")
        self.assertTrue(blocked.acks[0][1]["show_alert"])
        listing = self.request("POST", "/api/list", {"kind": "native"})[1]
        self.assertTrue(listing["items"][0]["archived"])

    def test_rejected_native_bad_override_never_appears_in_telegram(self):
        bad = deepcopy(NATIVE)
        bad["draft"]["overrides"] = {"charge.main.efb_voltage_v": 99.0}
        status, _ = self.request("POST", "/api/save", {"kind": "native", "recipe": bad})
        self.assertEqual(status, 422)
        self.assertEqual(self.native_drafts.list_drafts(), ())
        empty = self.call("native_draft_list", "recipes:nd:list")
        self.assertNotIn("recipes:nd:view:test_native:1", button_data(empty))


if __name__ == "__main__":
    unittest.main()
