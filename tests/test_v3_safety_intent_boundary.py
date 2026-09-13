import ast
import pathlib
import unittest

from runtime.charge import ChargeIntent, Measurements
from runtime.safety import SafetyContext, SafetyDecision, SafetyEngine, SafetyLimits


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
        self.assertEqual("VOLTAGE_LIMIT", decision.reason)

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
