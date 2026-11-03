"""Canonical native settings browser reflects real module-owned declarations."""
import tempfile
import unittest

from runtime.charge.programs.native_recipe_catalog import native_recipes
from runtime.charge.programs.native_recipe_parameters import native_recipe_parameters
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.ui.telegram.recipes import install_recipe_catalog_commands
from test_recipe_real_callback_chain import _App, _Call


class NativeParameterBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_native_profile_has_declared_bounded_settings(self):
        for entry in native_recipes():
            specs = native_recipe_parameters(entry.recipe_id)
            with self.subTest(entry=entry.recipe_id):
                self.assertGreaterEqual(len(specs), 5)
                self.assertEqual(len({spec.key for spec in specs}), len(specs))
                self.assertTrue(all(spec.minimum is not None and
                                    spec.maximum is not None for spec in specs))
                self.assertTrue(all(spec.minimum <= spec.default <= spec.maximum
                                    for spec in specs))
                if entry.intent == "diagnostic":
                    self.assertFalse(any(spec.key.startswith("charge.mix.")
                                         for spec in specs))
                else:
                    self.assertTrue(any(spec.key.startswith("charge.mix.")
                                        for spec in specs))

    async def test_parameter_callback_is_non_mutating_and_shows_real_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = RecipeCatalog(RecipeLibrary(root, max_voltage_v=15.5,
                                                  max_current_a=7.2))
            app = _App()
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = {h.callback.__name__: h.callback
                        for h in app.router.callback_query.handlers}
            call = _Call("recipes:native:params:native_efb_recovery")
            await handlers["native_recipe_parameters_view"](call)
            self.assertEqual(len(call.acks), 1)
            text, data = call.message.sent[0]
            self.assertIn("charge.main.efb_voltage_v", text)
            self.assertIn("charge.mix.efb_voltage_v", text)
            self.assertIn("Изменения пока не применяются", text)
            callbacks = [button.callback_data for row in
                         data["reply_markup"].inline_keyboard for button in row]
            self.assertEqual(callbacks, ["recipes:native:view:native_efb_recovery"])
            self.assertEqual(catalog.list_recipes(), ())

    async def test_unknown_native_parameters_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            app = _App()
            catalog = RecipeCatalog(RecipeLibrary(root, max_voltage_v=15.5,
                                                  max_current_a=7.2))
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = {h.callback.__name__: h.callback
                        for h in app.router.callback_query.handlers}
            call = _Call("recipes:native:params:unknown")
            await handlers["native_recipe_parameters_view"](call)
            self.assertTrue(call.acks[0][1].get("show_alert"))
            self.assertFalse(call.message.sent)

