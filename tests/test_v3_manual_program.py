import ast
import pathlib
import unittest

from runtime.charge import (
    BatteryProfile,
    ChargeDecisionShadow,
    ChargeEngine,
    ChargeIntent,
    ChargeState,
    ChemistryProfile,
    ComparisonResult,
    ManualProgram,
    ManualTargets,
    Measurements,
)


class V3ManualProgramTests(unittest.TestCase):
    def setUp(self):
        self.battery = BatteryProfile(ChemistryProfile.AGM, 80.0)
        self.state = ChargeState(stage="manual")
        self.measurements = Measurements(voltage=12.6, current=0.0, temperature=25.0, time=1.0)

    def test_manual_targets_map_to_intent(self):
        program = ManualProgram(self.battery, ManualTargets(14.7, 5.0, "manual", "MANUAL_START"))

        result = program.evaluate(self.state, self.measurements)

        self.assertEqual(ChargeIntent(14.7, 5.0, "manual", False, "MANUAL_START"), result)

    def test_manual_program_is_used_by_engine(self):
        engine = ChargeEngine(self.battery, ManualProgram(self.battery, ManualTargets(13.8, 1.0)))

        result = engine.evaluate(self.state, self.measurements)

        self.assertEqual(13.8, result.target_voltage)
        self.assertEqual(1.0, result.target_current)
        self.assertEqual("manual", result.next_stage)
        self.assertFalse(result.completed)

    def test_legacy_manual_comparison_detects_mismatch(self):
        engine = ChargeEngine(self.battery, ManualProgram(self.battery, ManualTargets(14.7, 5.0, "manual", "MANUAL_START")))
        comparison = ChargeDecisionShadow(self.battery, engine).compare(
            {"set_voltage": 14.6, "set_current": 5.0, "next_stage": "manual", "completed": False, "log_event": "MANUAL_START"},
            self.state,
            self.measurements,
        )

        self.assertIs(ComparisonResult.MISMATCH, comparison.result)
        self.assertEqual(("target_voltage",), comparison.mismatches)

    def test_manual_program_has_no_integration_imports_or_actuators(self):
        root = pathlib.Path(__file__).parents[1] / "runtime" / "charge" / "programs"
        forbidden = {"bot_legacy", "hass_api", "aiogram", "rd_control_mode", "safe_output", "turn_on", "turn_off", "set_voltage", "set_current"}
        for path in root.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertTrue(forbidden.isdisjoint(text.split()), path.name)
            tree = ast.parse(text, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden)

    def test_manual_targets_reject_non_positive_values(self):
        with self.assertRaises(ValueError):
            ManualTargets(0.0, 1.0)
        with self.assertRaises(ValueError):
            ManualTargets(14.7, -1.0)


if __name__ == "__main__":
    unittest.main()
