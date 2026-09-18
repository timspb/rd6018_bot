import ast
import pathlib
import unittest

from runtime.charge import (
    BatteryProfile,
    ChargeEngine,
    ChargeIntent,
    ChargeState,
    ChemistryProfile,
    Measurements,
)
from charge_parity_fixtures import legacy_mapping_to_intent


class V3LegacyParityFixtureTests(unittest.TestCase):
    def test_legacy_decision_maps_to_intent_through_engine(self):
        battery = BatteryProfile(ChemistryProfile.EFB, 72.0)

        def legacy_behavior(profile, state, measurements):
            self.assertIs(profile, battery)
            self.assertEqual("minimum", state.program)
            self.assertEqual(14.4, measurements.voltage)
            return {
                "set_voltage": 14.4,
                "set_current": 2.0,
                "next_stage": "delta",
                "completed": False,
                "log_event": "MINIMUM_HOLD",
            }

        legacy_intent = legacy_mapping_to_intent(legacy_behavior(battery, ChargeState(program="minimum"), Measurements(voltage=14.4, current=2.0, temperature=25.0, time=10.0)))
        result = ChargeEngine(battery, _FixtureProgram(legacy_intent)).evaluate(
            ChargeState(program="minimum", stage="main"),
            Measurements(voltage=14.4, current=2.0, temperature=25.0, time=10.0),
        )

        self.assertEqual(
            ChargeIntent(14.4, 2.0, "delta", False, "MINIMUM_HOLD"),
            result,
        )

    def test_legacy_actuator_result_is_rejected_at_boundary(self):
        battery = BatteryProfile(ChemistryProfile.AGM, 80.0)
        with self.assertRaises(ValueError):
            legacy_mapping_to_intent({"set_voltage": 14.4, "turn_on": True})

    def test_adapter_has_no_external_integration_imports(self):
        root = pathlib.Path(__file__).parents[1] / "runtime" / "charge"
        forbidden = {"bot_legacy", "hass_api", "aiogram", "rd_control_mode", "safe_output", "LegacyChargeProgramAdapter"}
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(forbidden.isdisjoint({a.name.split(".")[0] for a in node.names}))
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden)


class _FixtureProgram:
    def __init__(self, intent):
        self.intent = intent

    def evaluate(self, state, measurements):
        return self.intent


if __name__ == "__main__":
    unittest.main()
