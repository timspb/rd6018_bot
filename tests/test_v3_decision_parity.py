import unittest

from runtime.charge import ChargeIntent, Measurements
from runtime.charge.shadow import DecisionParityComparator, ParityStatus, V3DecisionSnapshot
from decision_parity_fixtures import from_mapping
from runtime.output import OutputIntentFactory
from runtime.safety import SafetyContext, SafetyEngine, SafetyLimits


class V3DecisionParityRepresentativeTests(unittest.TestCase):
    def setUp(self):
        self.safety = SafetyEngine(SafetyLimits(17.5, 12.0))
        self.measurements = Measurements(16.5, 2.0, 25.0, 100.0)

    def _compare(self, intent, legacy):
        safety = self.safety.evaluate(intent, self.measurements, SafetyContext())
        output = OutputIntentFactory().create(safety) if safety.allowed else None
        return DecisionParityComparator().compare(
            from_mapping(legacy),
            V3DecisionSnapshot.from_decisions(intent, safety, output),
        )

    def test_main_recovery_mix_and_completion_vectors(self):
        cases = (
            (ChargeIntent(14.8, 7.0, "main", False, "MAIN_ACTIVE"), "main"),
            (ChargeIntent(16.3, 1.4, "recovery", False, "MAIN_PLATEAU_RECOVERY"), "recovery"),
            (ChargeIntent(16.5, 2.1, "mix", False, "RECOVERY_EXHAUSTED_MIX"), "mix"),
            (ChargeIntent(completed=True, next_stage="done", reason="MIX_CV_HOLD_COMPLETE"), "done"),
        )
        for intent, stage in cases:
            with self.subTest(stage=stage):
                result = self._compare(intent, {
                    "phase": stage, "stage": stage, "transition": intent.reason,
                    "completed": intent.completed,
                    "enable": not intent.completed,
                    "target_voltage": intent.target_voltage,
                    "target_current": intent.target_current,
                    "safety_allowed": True,
                })
                self.assertEqual(ParityStatus.MATCH, result.status)

    def test_mismatch_reports_field_and_snapshot_aliases(self):
        result = self._compare(
            ChargeIntent(16.5, 2.1, "mix", False, "MIX_CC_DELTA_WAIT"),
            {"phase": "mix", "stage": "mix", "transition": "MIX_CC_DELTA_WAIT",
             "completed": False, "enable": True, "target_voltage": 16.5,
             "target_current": 2.0, "safety_allowed": True},
        )
        self.assertEqual(ParityStatus.MISMATCH, result.status)
        self.assertIn("target_current", result.fields)
        self.assertIs(result.v2_snapshot, result.v2_decision)
        self.assertIs(result.v3_snapshot, result.v3_decision)


if __name__ == "__main__":
    unittest.main()
