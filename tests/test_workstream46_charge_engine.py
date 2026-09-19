import unittest

from application.charge_engine import BatteryState, ChargeEngine, Phase, TelemetrySnapshot
from application.charge_program import BatteryProfile, ManualProgramInput, resolve_charge_program


def telemetry() -> TelemetrySnapshot:
    return TelemetrySnapshot(100.0, 14.7, 2.0, 23.0)


class ChargeEngineDomainTests(unittest.TestCase):
    def test_auto_programs_produce_deterministic_main_decisions(self):
        for chemistry in ("CALCIUM", "EFB", "AGM"):
            with self.subTest(chemistry=chemistry):
                program = resolve_charge_program(BatteryProfile("battery", chemistry, 72), "AUTO")
                engine = ChargeEngine(program)
                state = BatteryState(phase=Phase.MAIN)
                self.assertEqual(engine.evaluate(state, telemetry()), engine.evaluate(state, telemetry()))
                self.assertTrue(engine.evaluate(state, telemetry()).has_setpoints)
                self.assertEqual(engine.evaluate(state, telemetry()).current_phase, Phase.MAIN)

    def test_manual_baic72_decision_uses_program_values(self):
        manual = ManualProgramInput(14.1, 5.0, 17.5, 3.5, 0.6, 0.6, 4.0)
        program = resolve_charge_program(BatteryProfile("Baic72", "CA_CA", 72), "MANUAL", manual)
        decision = ChargeEngine(program).evaluate(BatteryState(phase=Phase.MIX), telemetry())
        self.assertEqual(decision.desired_voltage_v, 17.5)
        self.assertEqual(decision.desired_current_a, 3.5)

    def test_phase_transitions_are_explanatory(self):
        engine = ChargeEngine(resolve_charge_program(BatteryProfile("battery", "EFB", 72), "AUTO"))
        cases = (
            (BatteryState(Phase.PREP), Phase.MAIN),
            (BatteryState(Phase.MAIN, main_complete=True), Phase.MIX),
            (BatteryState(Phase.MIX, delta_confirmed=True), Phase.HOLD),
            (BatteryState(Phase.HOLD, hold_complete=True), Phase.SAFE_WAIT),
            (BatteryState(Phase.SAFE_WAIT, safe_wait_complete=True), Phase.DONE),
        )
        for state, expected in cases:
            with self.subTest(state=state.phase):
                decision = engine.evaluate(state, telemetry())
                self.assertEqual(decision.next_phase, expected)
                self.assertTrue(decision.reason)
                self.assertTrue(decision.next_transition_criteria)

    def test_desulfation_phase_is_supported_as_domain_state(self):
        engine = ChargeEngine(resolve_charge_program(BatteryProfile("battery", "AGM", 72), "AUTO"))
        decision = engine.evaluate(BatteryState(Phase.DESULFATION), telemetry())
        self.assertEqual(decision.current_phase, Phase.DESULFATION)
        self.assertIsNone(decision.desired_voltage_v)
        self.assertIn("no DESULFATION policy", decision.reason)

    def test_missing_telemetry_does_not_create_a_decision_setpoint(self):
        engine = ChargeEngine(resolve_charge_program(BatteryProfile("battery", "CALCIUM", 72), "AUTO"))
        stale = TelemetrySnapshot(100.0, 14.7, None, 23.0, fresh=False)
        decision = engine.evaluate(BatteryState(Phase.MAIN), stale)
        self.assertIsNone(decision.desired_voltage_v)
        self.assertIsNone(decision.desired_current_a)
        self.assertIn("stale", decision.reason)

    def test_engine_has_no_physical_or_v2_dependency(self):
        import application.charge_engine.engine as module

        with open(module.__file__, encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("ChargeControllerV2", "hass_api", "SafeOutputCoordinator", "turn_on", "turn_off"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
