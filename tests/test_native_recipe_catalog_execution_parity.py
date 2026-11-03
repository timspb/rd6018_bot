"""Every field offered in native recipe editor must be executable at START."""
import tempfile
import unittest

from runtime.charge.programs.native_recipe_catalog import native_recipes
from runtime.charge.programs.native_recipe_parameters import native_recipe_parameters
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_session import select_native_recipe_version


class NativeRecipeCatalogExecutionParityTests(unittest.TestCase):
    def test_every_visible_setting_is_accepted_by_existing_execution_contract(self):
        with tempfile.TemporaryDirectory() as root:
            lib = NativeRecipeDraftLibrary(root)
            for entry in native_recipes():
                specs = native_recipe_parameters(entry.recipe_id)
                for index, spec in enumerate(specs):
                    with self.subTest(recipe=entry.recipe_id, parameter=spec.key):
                        name = f"copy_{entry.recipe_id}_{index}"
                        lib.save(name, 1, {
                            "schema": 1, "base_recipe_id": entry.recipe_id,
                            "execution_kind": "native_authority",
                            "overrides": {spec.key: spec.default},
                        })
                        selected = select_native_recipe_version(
                            lib, name, 1, profile=entry.profile,
                            intent=entry.intent,
                        )
                        self.assertEqual(dict(selected.overrides)[spec.key], spec.default)

    def test_diagnostic_and_agm_do_not_offer_nonexistent_stage_controls(self):
        for entry in native_recipes():
            keys = {spec.key for spec in native_recipe_parameters(entry.recipe_id)}
            with self.subTest(entry=entry.recipe_id):
                if entry.intent == "diagnostic":
                    self.assertFalse(any(k.startswith("charge.safe_wait.") or
                                         k.startswith("charge.desulfation.") or
                                         k.startswith("charge.mix.") for k in keys))
                if entry.profile == "AGM":
                    self.assertNotIn("charge.main.default_voltage_v", keys)
                current = next(spec for spec in native_recipe_parameters(entry.recipe_id)
                               if spec.key == "charge.main.current_c_rate")
                self.assertEqual(current.maximum, 0.10)
