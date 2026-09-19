import unittest

from application.charge_card import ChargeCardFormatter, ChargeCardViewModel
from application.operator_state import (
    CCVState,
    OperatorStateSnapshot,
    PhaseLifecycleState,
    SafetyView,
    TelemetryView,
)


def snapshot(phase="MAIN", mode="AUTO", evidence=("minimum registered",), waiting=("hold_complete",)):
    return OperatorStateSnapshot(
        battery_identity="Baic72",
        battery_profile="Baic72",
        chemistry="CALCIUM",
        mode=mode,
        program_id="manual:Baic72",
        current_phase=phase,
        phase_state=PhaseLifecycleState.ACTIVE,
        phase_evidence=evidence,
        target_voltage_v=14.4 if phase == "MAIN" else 17.5,
        target_current_a=5.0 if phase == "MAIN" else 3.5,
        active_policies=("hold",),
        telemetry=TelemetryView(14.2, 4.8, 68.16, 32.0, CCVState.CC, 1.0, "FRESH"),
        safety=SafetyView("OK", "FRESH", "HIGH"),
        lifecycle_status="ACTIVE",
        session_id="session-75",
        trace_id="trace-75",
        explanation="phase explanation",
        waiting_conditions=waiting,
        next_transition="MIX",
    )


class ChargeCardV2Tests(unittest.TestCase):
    def render(self, state, **kwargs):
        model = ChargeCardViewModel.from_snapshot(state, **kwargs)
        return ChargeCardFormatter().format(model)

    def test_main_card(self):
        text = self.render(snapshot(), amp_hours=12.5, elapsed_seconds=3661, minimum_value=13.9, hold_remaining_seconds=120)
        self.assertEqual(len(text.splitlines()), 5)
        self.assertIn("🔋 Baic72 · MAIN  AUTO", text)
        self.assertIn("MIN=13.90 Hold=02m 00s", text)
        self.assertNotIn("RD6018", text)
        self.assertNotIn("ЗАРЯД", text)

    def test_mix_card_shows_min_max_and_conditions(self):
        text = self.render(snapshot("MIX", "MANUAL", evidence=("Delta complete",), waiting=("termination criteria",)), amp_hours=20.0, minimum_value=16.8, maximum_value=17.5, hold_remaining_seconds=7200)
        self.assertIn("🔋 Baic72 · MIX  MANUAL", text)
        self.assertIn("Delta complete", text)
        self.assertIn("MIN=16.80 MAX=17.50 Hold=2h 00m", text)

    def test_hold_card_shows_condition_and_timer(self):
        text = self.render(snapshot("HOLD", "AUTO", evidence=("Delta complete",), waiting=("continuous hold evidence",)), hold_remaining_seconds=90)
        self.assertIn("condition:", text)
        self.assertIn("continuous hold evidence", text)
        self.assertIn("Hold=01m 30s", text)

    def test_auto_and_manual_modes_are_preserved(self):
        self.assertIn("  AUTO", self.render(snapshot("MAIN", "AUTO")))
        self.assertIn("  MANUAL", self.render(snapshot("MAIN", "MANUAL")))

    def test_unknown_phase_and_values_are_visible(self):
        state = snapshot("UNKNOWN", "AUTO", evidence=(), waiting=())
        state = OperatorStateSnapshot(**{**state.__dict__, "current_phase": "UNKNOWN", "target_voltage_v": None, "target_current_a": None, "telemetry": TelemetryView(None, None, None, None, CCVState.UNKNOWN, None, "MISSING")})
        text = self.render(state)
        self.assertIn("UNKNOWN", text)
        self.assertNotIn("None", text)
        self.assertNotIn("\n\n", text)

    def test_diagnostics_are_not_part_of_charge_card(self):
        model = ChargeCardViewModel.from_snapshot(snapshot())
        self.assertFalse(hasattr(model, "diagnostics"))
        text = ChargeCardFormatter().format(model)
        self.assertNotIn("warnings", text.lower())
        self.assertNotIn("blockers", text.lower())


if __name__ == "__main__":
    unittest.main()
