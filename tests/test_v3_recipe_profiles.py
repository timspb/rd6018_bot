import unittest

from runtime.charge import BatteryProfile, ChemistryProfile, ChargeStrategy, Measurements, StrategyRuntimeState
from runtime.charge.profiles import RecipeDTO, RecipeRegistry, RecipeValidationError, RecipeOverrideError


class V3RecipeProfileTests(unittest.TestCase):
    def setUp(self):
        self.registry = RecipeRegistry()

    def test_factory_profiles_and_mapping(self):
        self.assertEqual(ChemistryProfile.AGM, self.registry.get_factory_recipe("AGM").chemistry)
        self.assertEqual(ChemistryProfile.EFB, self.registry.get_factory_recipe("EFB").chemistry)
        self.assertEqual(ChemistryProfile.CALCIUM, self.registry.get_factory_recipe("CA_CA").chemistry)
        self.assertEqual(ChemistryProfile.CALCIUM, self.registry.get_factory_recipe("FLOODED").chemistry)
        self.assertEqual(("AGM", "EFB", "CA_CA", "FLOODED", "CUSTOM"), self.registry.list_profiles())

    def test_valid_override_inherits_factory(self):
        base = self.registry.get_factory_recipe("AGM")
        custom = self.registry.resolve_profile("AGM", {"mix.cc.delta_voltage": 0.04})
        self.assertEqual("factory+override", custom.source)
        self.assertEqual(0.04, custom.recipe.mix.config.cc.delta_voltage)
        self.assertEqual(base.recipe.mix.config.cv.delta_current, custom.recipe.mix.config.cv.delta_current)

    def test_invalid_override_and_forbidden_policy_change_rejected(self):
        with self.assertRaises(RecipeOverrideError):
            self.registry.resolve_profile("AGM", {"recovery.attempt_budget": 0})
        with self.assertRaises(RecipeOverrideError):
            self.registry.resolve_profile("AGM", {"mix.cc.delta_voltage": -1})

    def test_dto_and_chemistry_validation(self):
        with self.assertRaises(RecipeValidationError):
            self.registry.create_custom_profile(RecipeDTO("", {}))
        with self.assertRaises(RecipeValidationError):
            self.registry.create_custom_profile(RecipeDTO("CUSTOM", {}, {}))
        custom = self.registry.create_custom_profile(RecipeDTO("CUSTOM", {"mix.cc.delta_voltage": 0.04}, "AGM"))
        self.assertEqual(ChemistryProfile.AGM, custom.chemistry)
        with self.assertRaises(ValueError):
            self.registry.get_factory_recipe("UNKNOWN")

    def test_validated_recipe_is_strategy_compatible(self):
        profile = self.registry.get_factory_recipe("EFB").to_battery_profile(70.0)
        strategy = ChargeStrategy(profile, profile.recipe)
        result = strategy.evaluate(StrategyRuntimeState(), Measurements(14.8, 7.0, 25.0, 0.0))
        self.assertEqual("main", result.next_stage)
        self.assertIsInstance(profile, BatteryProfile)


if __name__ == "__main__":
    unittest.main()
