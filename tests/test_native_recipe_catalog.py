"""Production recipe inventory must preserve the live owners and intents."""
from importlib.util import find_spec
import unittest

from runtime.charge.programs.native_recipe_catalog import (
    INTENTS, PROFILES, get_native_recipe, native_recipes,
)


class NativeRecipeCatalogTests(unittest.TestCase):
    def test_existing_profiles_and_intents_are_inventoried(self):
        entries = native_recipes()
        self.assertEqual(len(entries), len(PROFILES) * len(INTENTS))
        self.assertEqual(len({entry.recipe_id for entry in entries}), len(entries))
        self.assertEqual({(entry.profile, entry.intent) for entry in entries},
                         {(profile, intent) for profile in PROFILES for intent in INTENTS})

    def test_original_owners_remain_authoritative(self):
        for entry in native_recipes():
            self.assertEqual(get_native_recipe(entry.recipe_id), entry)
            self.assertEqual(entry.execution_kind, "native_authority")
            self.assertFalse(entry.editable)
            self.assertFalse(entry.executable_by_user_recipe_runner)
            for module in entry.owner_modules:
                self.assertIsNotNone(find_spec(module), module)

    def test_diagnostic_never_advertises_automatic_hv_stage(self):
        high_voltage = {"DESULFATION", "MIX"}
        for entry in native_recipes():
            if entry.intent == "diagnostic":
                self.assertFalse(high_voltage.intersection(entry.stages))
            else:
                self.assertIn("MAIN", entry.stages)

    def test_final_safe_wait_catalog_owner_matches_production_dispatch(self):
        from runtime.charge.programs.native_recipe_catalog import STAGE_OWNERS
        import inspect
        from runtime.charge.runtime import stage_authority
        from runtime.charge.runtime.final_safe_wait_authority import apply_final_safe_wait_authority

        owners = dict(STAGE_OWNERS)
        self.assertEqual(
            owners["FINAL_SAFE_WAIT"],
            "runtime.charge.runtime.final_safe_wait_authority",
        )
        self.assertTrue(callable(apply_final_safe_wait_authority))
        route_source = inspect.getsource(stage_authority.apply_authoritative_stage_tick)
        self.assertIn("from runtime.charge.runtime.final_safe_wait_authority import apply_final_safe_wait_authority", route_source)
        self.assertIn("return apply_final_safe_wait_authority(", route_source)
        for entry in native_recipes():
            if entry.intent != "diagnostic":
                self.assertIn(owners["FINAL_SAFE_WAIT"], entry.owner_modules)
            else:
                self.assertNotIn(owners["FINAL_SAFE_WAIT"], entry.owner_modules)

    def test_unknown_native_id_rejected(self):
        with self.assertRaises(KeyError):
            get_native_recipe("native_unknown")
