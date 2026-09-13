import unittest

from runtime.charge import ChargeIntent, Measurements
from runtime.charge.shadow import (
    DecisionParityComparator, LegacyDecisionAdapter, ParityStatus, V3DecisionSnapshot,
)
from runtime.output import OutputIntentFactory
from runtime.safety import SafetyContext, SafetyEngine, SafetyLimits


class V3V2DecisionParityTests(unittest.TestCase):
    def setUp(self):
        self.safety = SafetyEngine(SafetyLimits(17.5, 12.0))
        self.measurements = Measurements(14.4, 2.0, 25.0, 1.0)
        self.context = SafetyContext()

    def _v3(self, intent):
        decision = self.safety.evaluate(intent, self.measurements, self.context)
        output = OutputIntentFactory().create(decision) if decision.allowed else None
        return V3DecisionSnapshot.from_decisions(intent, decision, output)

    def test_main_representative_case_matches(self):
        intent = ChargeIntent(14.4, 2.0, "main", False, "MAIN_ACTIVE")
        v2 = LegacyDecisionAdapter().from_mapping({
            "phase": "main", "stage": "main", "transition": "MAIN_ACTIVE",
            "completed": False, "enable": True, "target_voltage": 14.4,
            "target_current": 2.0, "safety_allowed": True,
        })
        result = DecisionParityComparator().compare(v2, self._v3(intent))
        self.assertEqual(ParityStatus.MATCH, result.status)
        self.assertEqual((), result.fields)

    def test_recovery_and_mix_representative_vectors_are_decision_only(self):
        vectors = (
            ChargeIntent(16.3, 1.4, "recovery", False, "MAIN_PLATEAU_RECOVERY"),
            ChargeIntent(16.5, 2.1, "mix", False, "RECOVERY_EXHAUSTED_MIX"),
            ChargeIntent(completed=True, next_stage="done", reason="MIX_CV_HOLD_COMPLETE"),
        )
        for intent in vectors:
            snapshot = self._v3(intent)
            self.assertTrue(snapshot.safety_allowed)

    def test_intentional_mismatch_is_explicit(self):
        v2 = LegacyDecisionAdapter().from_mapping({"stage": "main", "target_voltage": 14.4, "target_current": 2.0})
        v3 = self._v3(ChargeIntent(14.5, 2.0, "main", False, "different"))
        result = DecisionParityComparator().compare(v2, v3)
        self.assertEqual(ParityStatus.MISMATCH, result.status)
        self.assertIn("target_voltage", result.fields)
        self.assertIn("transition", result.fields)

    def test_safety_denial_is_compared_without_output_path(self):
        decision = self.safety.evaluate(ChargeIntent(18.0, 2.0, "main"), self.measurements, self.context)
        v3 = V3DecisionSnapshot.from_decisions(ChargeIntent(18.0, 2.0, "main"), decision)
        v2 = LegacyDecisionAdapter().from_mapping({"phase": "main", "stage": "main", "transition": "VOLTAGE",
                                                    "safety_allowed": False, "violations": ["voltage"]})
        result = DecisionParityComparator().compare(v2, v3)
        self.assertEqual(ParityStatus.MATCH, result.status)


if __name__ == "__main__":
    unittest.main()
