import tempfile
import unittest

from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.ui.telegram.recipe_buttons import catalog_markup


class CatalogPaginationTests(unittest.TestCase):
    def test_more_than_thirty_recipes_are_accessible(self):
        with tempfile.TemporaryDirectory() as root:
            lib = RecipeLibrary(root, max_voltage_v=15.5, max_current_a=7.2)
            catalog = RecipeCatalog(lib)
            for n in range(45):
                lib.save({
                    "id": f"recipe_{n:02d}", "version": 1,
                    "steps": [{"action": "off", "params": {},
                               "until": {"after_seconds": 1}}],
                })
            first = catalog_markup(catalog)
            middle = catalog_markup(catalog, page=1)
            last = catalog_markup(catalog, page=2)
            f = [b for row in first.inline_keyboard for b in row]
            m = [b for row in middle.inline_keyboard for b in row]
            l = [b for row in last.inline_keyboard for b in row]
            for number, buttons in ((0, f), (1, m), (2, l)):
                self.assertTrue(any(b.callback_data == f"recipes:list:{number}" for b in buttons))
            self.assertTrue(any(b.callback_data == "recipes:list:1" for b in f))
            self.assertTrue(any(b.callback_data == "recipes:list:0" for b in m))
            self.assertTrue(any(b.callback_data == "recipes:list:2" for b in m))
            self.assertTrue(any(b.callback_data == "recipes:view:recipe_44:1" for b in l))
            self.assertTrue(any(b.callback_data == "recipes:create" for b in l))
            self.assertFalse(any(b.callback_data == "recipes:list:3" for b in l))
            all_views = [b.callback_data for buttons in (f,m,l) for b in buttons
                         if b.callback_data.startswith("recipes:view:")]
            self.assertEqual(len(set(all_views)), 45)
            self.assertTrue(all(len(b.encode("utf-8")) <= 64 for b in all_views))
            with self.assertRaises(ValueError):
                catalog_markup(catalog, page=3)

    def test_empty_catalog_keeps_creation(self):
        with tempfile.TemporaryDirectory() as root:
            cat = RecipeCatalog(RecipeLibrary(root, max_voltage_v=15.5, max_current_a=7.2))
            buttons = [b.callback_data for row in catalog_markup(cat).inline_keyboard for b in row]
            self.assertIn("recipes:create", buttons)
            self.assertIn("recipes:list:0", buttons)
