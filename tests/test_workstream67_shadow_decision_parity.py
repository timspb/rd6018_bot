import unittest

from application.charge_engine.models import TelemetrySnapshot
from application.shadow_decision_parity import (
    ShadowDecisionInput,
    ShadowDecisionParityEngine,
    ShadowDecisionView,
    ShadowParityStatus,
)


def context(telemetry=True):
    return ShadowDecisionInput(
        TelemetrySnapshot(1.0, 14.4, 5.0, 25.0) if telemetry else None,
        "CALCIUM", "MAIN", "auto:calcium", "ACTIVE", "session-67", 1.0,
    )


def view(program="auto:calcium", phase="MAIN", voltage=14.4, current=5.0, safety="ALLOW", intent=(
    ("voltage", 14.4), ("current", 5.0),
)):
    return ShadowDecisionView(program, phase, voltage, current, safety, intent)


class ShadowDecisionParityTests(unittest.TestCase):
    def setUp(self):
        self.engine = ShadowDecisionParityEngine()

    def test_identical_decision_is_match(self):
        result = self.engine.compare(context(), view(), view())
        self.assertEqual(result.status, ShadowParityStatus.MATCH)
        self.assertEqual(result.divergences, ())

    def test_different_program_is_divergence(self):
        result = self.engine.compare(context(), view(), view(program="auto:efb"))
        self.assertEqual(result.status, ShadowParityStatus.DIVERGENCE)
        self.assertEqual(result.divergences[0].field, "selected_program")
        self.assertEqual(result.divergences[0].session_id, "session-67")

    def test_different_phase_is_expected_difference_when_declared(self):
        result = self.engine.compare(
            context(), view(), view(phase="MIX"), expected_fields=("phase",)
        )
        self.assertEqual(result.status, ShadowParityStatus.EXPECTED_DIFFERENCE)

    def test_safety_divergence_is_recorded(self):
        result = self.engine.compare(context(), view(), view(safety="DENY"))
        self.assertEqual(result.status, ShadowParityStatus.DIVERGENCE)
        self.assertEqual(result.divergences[0].field, "safety_result")

    def test_missing_data_is_unknown_not_a_match(self):
        result = self.engine.compare(context(False), view(), view())
        self.assertEqual(result.status, ShadowParityStatus.UNKNOWN)

    def test_engine_has_no_influence_or_physical_dependencies(self):
        import application.shadow_decision_parity as module
        with open(module.__file__, encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("PhysicalExecution", "turn_on", "turn_off", "HA", "ESPHome", "Modbus", "controller.start"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
