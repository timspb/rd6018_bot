"""Native built-in catalog callbacks keep their owner and route boundary."""
import tempfile
import types
import unittest
from pathlib import Path

from aiogram import Router
from aiogram.enums import ParseMode

from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.ui.telegram import native_recipe_catalog_buttons as buttons
from runtime.ui.telegram import recipe_buttons
from runtime.ui.telegram import recipe_menu_view


class _App:
    def __init__(self):
        self.router = Router()
        self.ParseMode = ParseMode
        self.allowed = False
        self.checks = 0

    async def _check_chat_and_respond(self, _call):
        self.checks += 1
        return self.allowed


class _Call:
    data = "recipes:native:view:ca_ca_normal"

    def __init__(self):
        self.message = types.SimpleNamespace(answer=self._answer_message)
        self.answers = []

    async def _answer_message(self, *_args, **_kwargs):
        raise AssertionError("denied callback must not send a message")

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class NativeRecipeCatalogOwnerBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_native_markup_is_a_direct_compatibility_reexport(self):
        self.assertIs(recipe_buttons.native_recipe_markup,
                      recipe_menu_view.native_recipe_markup)

    async def test_callback_order_and_acl_precede_catalog_read(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = RecipeCatalog(RecipeLibrary(
                Path(root) / "recipes", max_voltage_v=15.5, max_current_a=7.2,
            ))
            app = _App()
            recipe_buttons.install_recipe_buttons(app, catalog=catalog)
            callbacks = [handler.callback.__name__
                         for handler in app.router.callback_query.handlers]
            expected = [
                "native_draft_list", "native_draft_view", "native_draft_history",
                "native_draft_edit", "native_draft_adjust", "native_draft_copy",
                "native_catalog", "native_recipe_details", "native_recipe_parameters_view",
                "check_recipe", "create_draft", "show_list", "show_recipe",
                "recipe_history", "recipe_duplicate", "recipe_archive_ask",
                "recipe_archive_confirm", "copy_help",
                "edit_menu", "change_threshold", "change_condition", "change_time",
                "change_step", "append_step", "adjust_step",
            ]
            self.assertEqual(callbacks, expected)

            recipe_buttons.install_recipe_buttons(app, catalog=catalog)
            self.assertEqual(len(app.router.callback_query.handlers), len(expected))

            original = buttons.get_native_recipe
            reads = []
            buttons.get_native_recipe = lambda recipe_id: reads.append(recipe_id)
            try:
                call = _Call()
                await callbacks_handler(app, "native_recipe_details")(call)
                self.assertEqual(app.checks, 1)
                self.assertEqual(reads, [])
                self.assertEqual(call.answers, [])
            finally:
                buttons.get_native_recipe = original


def callbacks_handler(app, name):
    return next(handler.callback for handler in app.router.callback_query.handlers
                if handler.callback.__name__ == name)
