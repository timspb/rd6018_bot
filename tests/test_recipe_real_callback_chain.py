"""Production callback-chain regression for non-energizing recipe draft creation."""
import tempfile
import types
import unittest

from aiogram import Router
from aiogram.enums import ParseMode

from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.ui.telegram.recipes import install_recipe_catalog_commands


class _App:
    def __init__(self):
        self.router = Router()
        self.ParseMode = ParseMode

    async def _check_chat_and_respond(self, call):
        return True


class _Message:
    def __init__(self):
        self.sent = []

    async def answer(self, text, **kwargs):
        self.sent.append((text, kwargs))
        return types.SimpleNamespace(message_id=100)


class _Call:
    def __init__(self, data):
        self.data = data
        self.message = _Message()
        self.acks = []

    async def answer(self, *args, **kwargs):
        self.acks.append((args, kwargs))


class RealRecipeCallbackChainTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_draft_to_editor_without_hardware_or_start(self):
        with tempfile.TemporaryDirectory() as path:
            catalog = RecipeCatalog(RecipeLibrary(
                path, max_voltage_v=15.5, max_current_a=7.2
            ))
            app = _App()
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = {h.callback.__name__: h.callback
                        for h in app.router.callback_query.handlers}

            create = _Call("recipes:create")
            await handlers["create_draft"](create)
            self.assertEqual(len(create.acks), 1)
            self.assertEqual(len(create.message.sent), 1)
            (name,) = catalog.list_recipes()
            recipe = catalog.library.load(name, 1)
            self.assertTrue(name.startswith("draft_"))
            self.assertEqual(recipe.steps[0]["action"], "off")

            buttons = create.message.sent[0][1]["reply_markup"].inline_keyboard
            data = [button.callback_data for row in buttons for button in row]
            self.assertIn(f"recipes:edit:{name}:1", data)

            edit = _Call(f"recipes:edit:{name}:1")
            await handlers["edit_menu"](edit)
            self.assertEqual(len(edit.message.sent), 1)
            buttons = edit.message.sent[0][1]["reply_markup"].inline_keyboard
            data = [button.callback_data for row in buttons for button in row]
            self.assertIn(f"recipes:append:{name}:1:set", data)
            self.assertTrue(all(len(value.encode("utf-8")) <= 64 for value in data))
            self.assertEqual(catalog.library.versions(name), (1,))