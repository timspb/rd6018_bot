import ast
import pathlib
import unittest

from runtime.charge import (
    BatteryProfile,
    ChargeEngine,
    ChargeIntent,
    ChargeProgram,
    ChargeState,
    ChemistryProfile,
    ComparisonResult,
    ChargeDecisionShadow,
    Measurements,
)
from charge_parity_fixtures import legacy_mapping_to_intent


class MatchingProgram(ChargeProgram):
    def evaluate(self, state, measurements):
        return ChargeIntent(14.4, 2.0, "delta", False, "MINIMUM_HOLD")


class MismatchingProgram(ChargeProgram):
    def evaluate(self, state, measurements):
        return ChargeIntent(14.5, 2.0, "delta", False, "different")


class V3ShadowComparisonTests(unittest.TestCase):
    def setUp(self):
        self.battery = BatteryProfile(ChemistryProfile.EFB, 72.0)
        self.state = ChargeState(program="minimum", stage="main")
        self.measurements = Measurements(voltage=14.4, current=2.0, temperature=25.0, time=1.0)
        self.legacy = {
            "set_voltage": 14.4,
            "set_current": 2.0,
            "next_stage": "delta",
            "completed": False,
            "log_event": "MINIMUM_HOLD",
        }

    def test_identical_legacy_and_new_decision_matches(self):
        shadow = ChargeDecisionShadow(self.battery, ChargeEngine(self.battery, MatchingProgram()))

        comparison = shadow.compare(legacy_mapping_to_intent(self.legacy), self.state, self.measurements)

        self.assertIs(ComparisonResult.MATCH, comparison.result)
        self.assertEqual((), comparison.mismatches)

    def test_mismatch_is_reported_by_field(self):
        shadow = ChargeDecisionShadow(self.battery, ChargeEngine(self.battery, MismatchingProgram()))

        comparison = shadow.compare(legacy_mapping_to_intent(self.legacy), self.state, self.measurements)

        self.assertIs(ComparisonResult.MISMATCH, comparison.result)
        self.assertEqual(("target_voltage", "reason"), comparison.mismatches)

    def test_shadow_source_has_no_actuator_or_external_imports(self):
        root = pathlib.Path(__file__).parents[1] / "runtime" / "charge" / "shadow"
        forbidden = {"bot_legacy", "hass_api", "aiogram", "rd_control_mode", "safe_output", "turn_on", "turn_off", "set_voltage", "set_current"}
        for path in root.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertTrue(forbidden.isdisjoint(text.split()), path.name)
            tree = ast.parse(text, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden)


if __name__ == "__main__":
    unittest.main()
