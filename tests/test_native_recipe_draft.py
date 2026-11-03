"""Native setting drafts have exact types and cannot mutate live programs."""
import unittest

from runtime.charge.programs.native_recipe_catalog import native_recipes
from runtime.charge.programs.native_recipe_draft import validate_native_draft
from runtime.charge.programs.native_recipe_parameters import native_recipe_parameters


def document(recipe_id, overrides):
    return {"schema": 1, "base_recipe_id": recipe_id,
            "execution_kind": "native_authority", "overrides": overrides}


class NativeDraftTests(unittest.TestCase):
    def test_all_twelve_variants_validate_and_roundtrip_without_activation(self):
        for entry in native_recipes():
            available = native_recipe_parameters(entry.recipe_id)
            key = available[0].key
            draft = validate_native_draft(document(entry.recipe_id, {
                key: available[0].default,
            }))
            with self.subTest(recipe=entry.recipe_id):
                self.assertEqual(validate_native_draft(draft.as_document()), draft)
                self.assertEqual(draft.base_recipe_id, entry.recipe_id)
                self.assertEqual(draft.as_document()["execution_kind"], "native_authority")

    def test_invalid_numeric_types_limits_and_unknown_fields(self):
        recipe = "native_ca_ca_normal"
        key = native_recipe_parameters(recipe)[0].key
        for value in (None, True, "14.7", 14, float("nan"),
                      float("inf"), -1.0, 100.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_native_draft(document(recipe, {key: value}))
        for key in ("charge.mix.agm_voltage_v", "__dict__", "charge.other"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_native_draft(document(recipe, {key: 15.0}))
        with self.assertRaises(ValueError):
            validate_native_draft(document("native_agm_diagnostic",
                                           {"charge.mix.agm_voltage_v": 16.3}))
        with self.assertRaises(ValueError):
            validate_native_draft({**document(recipe, {}), "turn_on": True})

    def test_original_chemistry_and_intent_are_never_overridden(self):
        for entry in native_recipes():
            with self.subTest(entry=entry.recipe_id):
                draft = validate_native_draft(document(entry.recipe_id, {}))
                self.assertFalse(hasattr(draft, "apply"))
                self.assertFalse(hasattr(draft, "start"))
                self.assertEqual(draft.overrides, ())
