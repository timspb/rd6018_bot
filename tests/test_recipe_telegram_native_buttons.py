"""Source-only Telegram native draft parameter buttons, no hardware or START."""
from __future__ import annotations

import tempfile
import unittest

from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.ui.telegram.recipes import install_recipe_catalog_commands
from test_recipe_real_callback_chain import _App, _Call


def _data(call):
    return [
        button.callback_data
        for _, opts in call.message.sent
        for row in opts["reply_markup"].inline_keyboard
        for button in row
    ]


class NativeButtonEditorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = self.tmp.name
        self.catalog = RecipeCatalog(RecipeLibrary(
            root + "/recipes", max_voltage_v=15.5, max_current_a=7.2))
        self.drafts = NativeRecipeDraftLibrary(root + "/native_recipe_drafts")
        self.app = _App()
        install_recipe_catalog_commands(self.app, catalog=self.catalog)
        self.handlers = {
            h.callback.__name__: h.callback
            for h in self.app.router.callback_query.handlers
        }
        self.drafts.save("trial", 1, {
            "schema": 1, "base_recipe_id": "native_efb_normal",
            "execution_kind": "native_authority", "overrides": {},
        })

    async def test_buttons_create_immutable_revision_then_stale_rejected(self):
        view = _Call("recipes:nd:view:trial:1")
        await self.handlers["native_draft_view"](view)
        self.assertEqual(len(view.acks), 1)
        self.assertIn("recipes:nd:edit:trial:1:0", _data(view))
        edit = _Call("recipes:nd:edit:trial:1:0")
        await self.handlers["native_draft_edit"](edit)
        controls = [v for v in _data(edit) if v.startswith("recipes:nd:adjust:")]
        self.assertTrue(controls)
        self.assertTrue(all(len(v.encode("utf-8")) <= 64 for v in _data(edit)))
        press = _Call(next(v for v in controls if v.endswith(":up")))
        await self.handlers["native_draft_adjust"](press)
        self.assertEqual(len(press.acks), 1)
        self.assertEqual(self.drafts.versions("trial"), (1, 2))
        old = self.drafts.load("trial", 1)
        new = self.drafts.load("trial", 2)
        self.assertEqual(dict(old.overrides), {})
        self.assertTrue(dict(new.overrides))
        self.assertEqual(self.catalog.list_recipes(), ())
        self.assertIn("не запускалась", press.message.sent[0][0])
        retry = _Call(press.data)
        await self.handlers["native_draft_adjust"](retry)
        self.assertFalse(retry.message.sent)
        self.assertTrue(retry.acks[0][1]["show_alert"])
        self.assertEqual(self.drafts.versions("trial"), (1, 2))

    async def test_archive_blocks_editor_and_mutation(self):
        self.drafts.archive("trial")
        edit = _Call("recipes:nd:edit:trial:1:0")
        await self.handlers["native_draft_edit"](edit)
        self.assertTrue(edit.acks[0][1]["show_alert"])
        adjust = _Call("recipes:nd:adjust:trial:1:0:up")
        await self.handlers["native_draft_adjust"](adjust)
        self.assertTrue(adjust.acks[0][1]["show_alert"])
        self.assertEqual(self.drafts.versions("trial"), (1,))

    async def test_bad_index_direction_and_revision_are_rejected(self):
        for data in (
            "recipes:nd:adjust:trial:1:999:up",
            "recipes:nd:adjust:trial:1:0:other",
            "recipes:nd:edit:trial:1:999",
            "recipes:nd:edit:trial:0:0",
        ):
            with self.subTest(data=data):
                call = _Call(data)
                handler = (self.handlers["native_draft_edit"]
                           if ":edit:" in data else self.handlers["native_draft_adjust"])
                await handler(call)
                self.assertFalse(call.message.sent)
                self.assertTrue(call.acks[0][1]["show_alert"])
        self.assertEqual(self.drafts.versions("trial"), (1,))

    async def test_acl_denied_no_mutation(self):
        class Denied(_App):
            async def _check_chat_and_respond(self, call):
                return False
        app = Denied()
        install_recipe_catalog_commands(app, catalog=self.catalog)
        handlers = {h.callback.__name__: h.callback
                    for h in app.router.callback_query.handlers}
        for key, data in (
            ("native_draft_edit", "recipes:nd:edit:trial:1:0"),
            ("native_draft_adjust", "recipes:nd:adjust:trial:1:0:up"),
        ):
            call = _Call(data)
            await handlers[key](call)
            self.assertFalse(call.message.sent)
        self.assertEqual(self.drafts.versions("trial"), (1,))


if __name__ == "__main__":
    unittest.main()
