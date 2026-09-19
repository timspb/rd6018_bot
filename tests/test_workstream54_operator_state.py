import unittest

from application.charge_engine import TelemetrySnapshot
from application.charge_lifecycle import ChargeLifecycleSnapshot, DeltaState, HoldState, SafetyState
from application.charge_program import BatteryProfile, ManualProgramInput, resolve_charge_program
from application.operator_state import CCVState, OperatorStateBuilder, PhaseLifecycleState, SafetyView


def telemetry(fresh=True):
    return TelemetrySnapshot(100.0, 14.2 if fresh else None, 2.0 if fresh else None, 23.0 if fresh else None, fresh=fresh)


def lifecycle(phase="MAIN"):
    return ChargeLifecycleSnapshot("s-1", "Baic72", "manual:Baic72", phase, 10.0, ("entry confirmed",), DeltaState("IDLE"), HoldState("IDLE"), SafetyState("NORMAL"), 99.0, "t-1")


class OperatorStateCanonicalTests(unittest.TestCase):
    def test_auto_profiles_have_canonical_program_state(self):
        for chemistry in ("CALCIUM", "EFB", "AGM"):
            program = resolve_charge_program(BatteryProfile("battery", chemistry, 72), "AUTO")
            state = OperatorStateBuilder().build(program, phase="main", telemetry=telemetry(), safety=SafetyView("NORMAL", "FRESH", "HIGH"))
            self.assertEqual(state.mode, "AUTO")
            self.assertEqual(state.chemistry, chemistry)
            self.assertEqual(state.program_id, program.program_id)

    def test_manual_baic72_uses_explicit_program_values(self):
        manual = ManualProgramInput(14.1, 5.0, 17.5, 3.5, .6, .6, 4.0)
        program = resolve_charge_program(BatteryProfile("Baic72", "CA_CA", 72), "MANUAL", manual)
        state = OperatorStateBuilder().build(program, phase="mix", telemetry=telemetry(), lifecycle=lifecycle("MIX"), ccv_state=CCVState.CV)
        self.assertEqual(state.battery_identity, "Baic72")
        self.assertEqual(state.target_voltage_v, 17.5)
        self.assertEqual(state.lifecycle_status, "RESUME_EXISTING")

    def test_active_restored_and_ambiguous_lifecycle(self):
        program = resolve_charge_program(BatteryProfile("battery", "EFB", 72), "AUTO")
        builder = OperatorStateBuilder()
        active = builder.build(program, phase="main", telemetry=telemetry(), lifecycle=lifecycle("MAIN"))
        ambiguous = builder.build(program, phase="main", telemetry=telemetry(), lifecycle=None)
        self.assertEqual(active.session_id, "s-1")
        self.assertEqual(ambiguous.lifecycle_status, "AMBIGUOUS")

    def test_stale_and_missing_telemetry_are_explicit(self):
        program = resolve_charge_program(BatteryProfile("battery", "AGM", 72), "AUTO")
        builder = OperatorStateBuilder()
        stale = builder.build(program, phase="main", telemetry=TelemetrySnapshot(100, None, None, None, fresh=True), phase_state=PhaseLifecycleState.WAITING)
        missing = builder.build(program, phase="main", telemetry=TelemetrySnapshot(100, None, None, None, fresh=False))
        self.assertEqual(stale.telemetry.freshness, "STALE")
        self.assertEqual(missing.telemetry.freshness, "MISSING")
        self.assertEqual(stale.current_phase, "main")


if __name__ == "__main__":
    unittest.main()
