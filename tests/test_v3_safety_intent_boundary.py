import ast
import pathlib
import unittest

from runtime.charge import BatteryProfile, ChargeIntent, ChargeLimits, ChemistryProfile, Measurements
from runtime.charge.profiles import RecipeRegistry
from runtime.safety import SafetyContext, SafetyDecision, SafetyEngine, SafetyLimits, SafetyViolation
from runtime.output import OutputAction, SafeOutputIntent


class V3SafetyIntentBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.engine = SafetyEngine(SafetyLimits(max_voltage=15.0, max_current=8.0, max_temperature=45.0))
        self.measurements = Measurements(14.4, 2.0, 25.0, 1.0)
        self.context = SafetyContext()

    def test_accepts_valid_intent_without_applying_it(self):
        decision = self.engine.evaluate(ChargeIntent(14.4, 2.0, "minimum", False, "active"), self.measurements, self.context)

        self.assertIsInstance(decision, SafetyDecision)
        self.assertTrue(decision.accepted)
        self.assertEqual("ACCEPTED", decision.reason)
        self.assertEqual(15.0, decision.limits_applied["max_voltage"])
        self.assertEqual(8.0, decision.limits_applied["max_current"])

    def test_rejects_limit_violation(self):
        decision = self.engine.evaluate(ChargeIntent(15.1, 2.0, "minimum", False, "active"), self.measurements, self.context)

        self.assertFalse(decision.accepted)
        self.assertEqual("VOLTAGE", decision.reason)

    def test_rejects_stale_measurement(self):
        engine = SafetyEngine(SafetyLimits(15.0, 8.0, telemetry_max_age_seconds=30.0))
        decision = engine.evaluate(ChargeIntent(14.4, 2.0, "minimum"), Measurements(14.4, 2.0, 25.0, 10.0), SafetyContext(now=50.0))
        self.assertFalse(decision.allowed)
        self.assertEqual("TELEMETRY_STALE", decision.reason)
        self.assertEqual("telemetry_stale", decision.violations[0].type)

    def test_rejects_invalid_recipe_phase_and_mix_timeout(self):
        invalid_recipe = BatteryProfile(ChemistryProfile.AGM, 70.0)
        decision = self.engine.evaluate(
            ChargeIntent(14.4, 2.0, "mix", False, "MIX_TIMEOUT"), self.measurements,
            SafetyContext(profile=invalid_recipe, allowed_next_stages=frozenset({"main"})),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual({"phase_transition", "mix_timeout", "recipe"}, {item.type for item in decision.violations})

    def test_rejects_chemistry_envelope(self):
        recipe = RecipeRegistry().get_factory_recipe("AGM").to_battery_profile(70.0)
        profile = BatteryProfile(recipe.chemistry, recipe.capacity_ah, recipe=recipe.recipe,
                                 limits=ChargeLimits(14.5, 14.4, 13.8, 8.0))
        decision = self.engine.evaluate(ChargeIntent(14.6, 2.0, "main"), self.measurements, SafetyContext(profile=profile))
        self.assertFalse(decision.allowed)
        self.assertEqual("CHEMISTRY_VOLTAGE", decision.reason)
        self.assertIn("chemistry_voltage", {item.type for item in decision.violations})

    def test_output_contract_is_data_only(self):
        output_intent = SafeOutputIntent(OutputAction.ENABLE, 14.4, 2.0)
        self.assertEqual(OutputAction.ENABLE, output_intent.action)
        self.assertIsInstance(SafetyViolation("test", "test"), SafetyViolation)

    def test_rejects_invalid_context_and_accepts_safe_completion(self):
        rejected = self.engine.evaluate(
            ChargeIntent(14.4, 2.0, "minimum", False, "active"),
            self.measurements,
            SafetyContext(telemetry_valid=False),
        )
        completed = self.engine.evaluate(ChargeIntent(completed=True, next_stage="stopped", reason="stop"), self.measurements, self.context)

        self.assertFalse(rejected.accepted)
        self.assertEqual("TELEMETRY_INVALID", rejected.reason)
        self.assertTrue(completed.accepted)

    def test_safety_boundary_has_no_external_or_actuator_imports(self):
        path = pathlib.Path(__file__).parents[1] / "runtime" / "safety" / "engine.py"
        text = path.read_text(encoding="utf-8")
        forbidden = {"bot_legacy", "hass_api", "aiogram", "rd_control_mode", "turn_on", "turn_off", "set_voltage", "set_current"}
        self.assertTrue(forbidden.isdisjoint(text.split()))
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden)


if __name__ == "__main__":
    unittest.main()
