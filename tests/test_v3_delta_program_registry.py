import ast
import pathlib
import unittest

from runtime.charge import (
    BatteryProfile,
    ChargeEngine,
    ChargeIntent,
    ChargeState,
    ChemistryProfile,
    DeltaConfig,
    DeltaProgram,
    DeltaState,
    Measurements,
    ManualTargets,
    MinimumConfig,
    ProgramRegistry,
)


class V3DeltaProgramRegistryTests(unittest.TestCase):
    def setUp(self):
        self.battery = BatteryProfile(ChemistryProfile.AGM, 80.0)
        self.config = DeltaConfig(14.4, 2.0, "CV", 2.0, 0.3, confirmations_required=2, hold_seconds=10.0)

    def test_delta_state_transitions_and_intents(self):
        program = DeltaProgram(self.battery, self.config)

        entered = program.evaluate(ChargeState(stage="unarmed"), Measurements(14.4, 2.0, 25.0, 0.0))
        waiting = program.evaluate(ChargeState(stage="tracking"), Measurements(14.4, 1.9, 25.0, 1.0))
        confirmed = program.evaluate(ChargeState(stage="tracking", timers={"delta_confirmations": 1}), Measurements(14.4, 1.6, 25.0, 2.0))
        complete = program.evaluate(ChargeState(stage="confirmed_hold", timers={"delta_hold_started": 2.0}), Measurements(14.4, 1.6, 25.0, 12.0))

        self.assertEqual(DeltaState.TRACKING.value, entered.next_stage)
        self.assertEqual("DELTA_HOLD_WAIT", waiting.reason)
        self.assertEqual(DeltaState.CONFIRMED_HOLD.value, confirmed.next_stage)
        self.assertTrue(complete.completed)
        self.assertEqual("DELTA_COMPLETE", complete.reason)

    def test_delta_invalid_measurements_stop(self):
        result = DeltaProgram(self.battery, self.config).evaluate(
            ChargeState(stage="tracking"), Measurements(None, None, 25.0, 1.0)
        )

        self.assertEqual(ChargeIntent(None, None, "stopped", True, "DELTA_EVIDENCE_INVALID"), result)

    def test_registry_registers_and_looks_up_three_programs(self):
        registry = ProgramRegistry.with_defaults()

        self.assertEqual(("delta", "manual", "minimum"), registry.available())
        self.assertIsInstance(registry.create("delta", self.battery, self.config), DeltaProgram)
        self.assertIsInstance(registry.create("manual", self.battery, ManualTargets(14.4, 2.0)), object)
        self.assertIsInstance(registry.create("minimum", self.battery, MinimumConfig(14.4, 2.0, 0.3)), object)
        with self.assertRaises(KeyError):
            registry.get("unknown")

    def test_engine_selects_registered_program_and_returns_intent(self):
        engine = ChargeEngine(
            self.battery,
            registry=ProgramRegistry.with_defaults(),
            program_name="delta",
            program_config=self.config,
        )

        result = engine.evaluate(ChargeState(stage="unarmed"), Measurements(14.4, 2.0, 25.0, 0.0))

        self.assertIsInstance(result, ChargeIntent)
        self.assertEqual("tracking", result.next_stage)

    def test_domain_files_have_no_external_or_actuator_imports(self):
        root = pathlib.Path(__file__).parents[1] / "runtime" / "charge"
        paths = [root / "programs" / "delta.py", root / "registry.py"]
        forbidden = {"bot_legacy", "hass_api", "aiogram", "rd_control_mode", "safe_output", "turn_on", "turn_off", "set_voltage", "set_current"}
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden)


if __name__ == "__main__":
    unittest.main()
