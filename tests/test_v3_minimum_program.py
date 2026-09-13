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
    Measurements,
    MinimumConfig,
    MinimumProgram,
)


class V3MinimumProgramTests(unittest.TestCase):
    def setUp(self):
        self.battery = BatteryProfile(ChemistryProfile.EFB, 72.0)
        self.config = MinimumConfig(14.4, 5.0, 0.3, 14.2)
        self.state = ChargeState(stage="main")

    def test_creation_and_active_stage_transition(self):
        program = MinimumProgram(self.battery, self.config)

        result = program.evaluate(self.state, Measurements(14.0, 2.0, 25.0, 1.0))

        self.assertEqual(ChargeIntent(14.4, 5.0, "minimum", False, "MINIMUM_ACTIVE"), result)

    def test_completion_transitions_stage_and_sets_completed(self):
        program = MinimumProgram(self.battery, self.config)

        result = program.evaluate(self.state, Measurements(14.3, 0.2, 25.0, 2.0))

        self.assertTrue(result.completed)
        self.assertEqual("delta", result.next_stage)
        self.assertEqual("MINIMUM_COMPLETE", result.reason)

    def test_shadow_matches_representative_legacy_minimum(self):
        program = MinimumProgram(self.battery, self.config)
        shadow = ChargeDecisionShadow(self.battery, ChargeEngine(self.battery, program))
        measurements = Measurements(14.3, 0.2, 25.0, 2.0)

        comparison = shadow.compare(
            {
                "set_voltage": 14.4,
                "set_current": 5.0,
                "next_stage": "delta",
                "completed": True,
                "log_event": "MINIMUM_COMPLETE",
            },
            self.state,
            measurements,
        )

        self.assertIs(ComparisonResult.MATCH, comparison.result)
        self.assertEqual((), comparison.mismatches)

    def test_mismatch_is_explicitly_reported(self):
        program = MinimumProgram(self.battery, self.config)
        shadow = ChargeDecisionShadow(self.battery, ChargeEngine(self.battery, program))

        comparison = shadow.compare(
            {"set_voltage": 14.3, "set_current": 5.0, "next_stage": "delta", "completed": True, "log_event": "MINIMUM_COMPLETE"},
            self.state,
            Measurements(14.3, 0.2, 25.0, 2.0),
        )

        self.assertIs(ComparisonResult.MISMATCH, comparison.result)
        self.assertEqual(("target_voltage",), comparison.mismatches)

    def test_program_has_no_integration_or_actuator_imports(self):
        path = pathlib.Path(__file__).parents[1] / "runtime" / "charge" / "programs" / "minimum.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden = {"bot_legacy", "hass_api", "aiogram", "rd_control_mode", "safe_output"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(forbidden.isdisjoint({a.name.split(".")[0] for a in node.names}))
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden)


if __name__ == "__main__":
    unittest.main()
