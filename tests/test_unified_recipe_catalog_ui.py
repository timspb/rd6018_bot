"""Read-only native recipe browser does not mutate user library or charge state."""
import tempfile
import unittest

from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.ui.telegram.recipe_buttons import catalog_markup, native_recipe_markup
from runtime.ui.telegram.recipes import install_recipe_catalog_commands
from test_recipe_real_callback_chain import _App, _Call


class UnifiedRecipeCatalogUITests(unittest.IsolatedAsyncioTestCase):
    async def test_native_browser_is_read_only_and_separate_from_user_recipes(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = RecipeCatalog(RecipeLibrary(root, max_voltage_v=15.5,
                                                  max_current_a=7.2))
            top = [b.callback_data for row in catalog_markup(catalog).inline_keyboard
                   for b in row]
            self.assertIn("recipes:create", top)
            self.assertIn("recipes:native:list", top)
            native = [b.callback_data for row in native_recipe_markup().inline_keyboard
                      for b in row]
            views = [v for v in native if v.startswith("recipes:native:view:")]
            self.assertEqual(len(views), 12)
            self.assertEqual(len(set(views)), 12)
            self.assertTrue(all(len(v.encode()) <= 64 for v in native))
            self.assertFalse(any(v.startswith("recipes:edit:") or
                                 v == "v2_battery_start" for v in native))

            app = _App()
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = {h.callback.__name__: h.callback
                        for h in app.router.callback_query.handlers}
            listing = _Call("recipes:native:list")
            await handlers["native_catalog"](listing)
            self.assertEqual(len(listing.acks), 1)
            self.assertEqual(len(listing.message.sent), 1)
            self.assertIn("Штатные программы", listing.message.sent[0][0])
            view = _Call(views[0])
            await handlers["native_recipe_details"](view)
            self.assertEqual(len(view.acks), 1)
            self.assertIn("Редактирование и запуск", view.message.sent[0][0])
            self.assertEqual(catalog.list_recipes(), ())

    async def test_unknown_native_id_is_rejected_without_data_changes(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = RecipeCatalog(RecipeLibrary(root, max_voltage_v=15.5,
                                                  max_current_a=7.2))
            app = _App()
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = {h.callback.__name__: h.callback
                        for h in app.router.callback_query.handlers}
            view = _Call("recipes:native:view:native_no_such_recipe")
            await handlers["native_recipe_details"](view)
            self.assertEqual(len(view.message.sent), 0)
            self.assertTrue(view.acks[0][1].get("show_alert"))
            self.assertEqual(catalog.list_recipes(), ())

