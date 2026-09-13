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
    DeltaRuntimeState,
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

        entered = program.evaluate(ChargeState(), Measurements(14.4, 2.0, 25.0, 0.0))
        waiting = program.evaluate(ChargeState(), Measurements(14.4, 2.1, 25.0, 1.0))
        program.evaluate(ChargeState(), Measurements(14.4, 2.3, 25.0, 2.0))
        confirmed = program.evaluate(ChargeState(), Measurements(14.4, 2.3, 25.0, 3.0))
        complete = program.evaluate(ChargeState(), Measurements(14.4, 2.3, 25.0, 13.0))

        self.assertEqual(DeltaState.TRACKING.value, entered.next_stage)
        self.assertEqual("DELTA_HOLD_WAIT", waiting.reason)
        self.assertEqual(DeltaState.CONFIRMED_HOLD.value, confirmed.next_stage)
        self.assertTrue(complete.completed)
        self.assertEqual("DELTA_COMPLETE", complete.reason)

    def test_delta_invalid_measurements_stop(self):
        program = DeltaProgram(self.battery, self.config, DeltaRuntimeState(phase="tracking", observed_imin=1.0))
        result = program.evaluate(
            ChargeState(), Measurements(None, None, 25.0, 1.0)
        )

        self.assertEqual(ChargeIntent(None, None, "stopped", True, "DELTA_EVIDENCE_INVALID"), result)

    def test_cc_captures_observed_current_at_vmax_and_uses_current_drop(self):
        config = DeltaConfig(16.5, 2.0, "CC", 16.5, 0.03, confirmations_required=2, hold_seconds=10.0)
        program = DeltaProgram(self.battery, config)
        program.evaluate(ChargeState(), Measurements(16.5, 2.0, 25.0, 0.0))
        program.evaluate(ChargeState(), Measurements(16.47, 1.0, 25.0, 1.0))
        result = program.evaluate(ChargeState(), Measurements(16.46, 1.0, 25.0, 2.0))
        self.assertEqual("DELTA_HOLD_START", result.reason)
        self.assertEqual(2.0, program.runtime_state.observed_reference_current)

    def test_configured_reference_is_only_extremum_gate(self):
        program = DeltaProgram(self.battery, self.config)
        result = program.evaluate(ChargeState(), Measurements(14.4, 2.1, 25.0, 0.0))
        self.assertEqual("DELTA_WAIT_EXTREMUM", result.reason)

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
