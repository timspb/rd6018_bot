import unittest

from first_stage_evidence import FirstStageAssessment, FirstStageState
from legacy_transition_audit import TransitionAuditSeverity, audit_legacy_transition


def assessment(state: FirstStageState, reason: str = "evidence") -> FirstStageAssessment:
    return FirstStageAssessment(
        state=state,
        current_c_rate=0.005,
        tail_threshold_a=0.28,
        tail_threshold_c=0.004,
        near_target=True,
        reason=reason,
    )


class LegacyTransitionAuditTests(unittest.TestCase):
    def test_non_hv_transition_is_ignored(self):
        self.assertIsNone(
            audit_legacy_transition(
                stage_before="Main Charge",
                stage_after="Done",
                first_stage=assessment(FirstStageState.TAIL_READY),
            )
        )

    def test_main_to_hv_without_evidence_requires_review(self):
        result = audit_legacy_transition(
            stage_before="Main Charge",
            stage_after="Десульфатация",
            first_stage=None,
        )
        self.assertEqual(result.severity, TransitionAuditSeverity.REVIEW)
        self.assertIn("without_v2_evidence", result.code)

    def test_tail_still_evolving_marks_legacy_escalation_for_review(self):
        result = audit_legacy_transition(
            stage_before="Main Charge",
            stage_after="Mix Mode",
            first_stage=assessment(FirstStageState.BULK_OR_TAPER),
        )
        self.assertEqual(result.severity, TransitionAuditSeverity.REVIEW)
        self.assertEqual(result.code, "legacy_hv_escalation_while_tail_evolving")

    def test_thermal_instability_marks_hv_escalation_as_safety_issue(self):
        result = audit_legacy_transition(
            stage_before="Main Charge",
            stage_after="recovery",
            first_stage=assessment(
                FirstStageState.THERMALLY_UNSTABLE,
                "CV current reversal with accelerating temperature",
            ),
        )
        self.assertEqual(result.severity, TransitionAuditSeverity.SAFETY)
        self.assertEqual(result.code, "legacy_hv_escalation_during_thermal_instability")

    def test_voltage_instability_marks_hv_escalation_as_safety_issue(self):
        result = audit_legacy_transition(
            stage_before="Main Charge",
            stage_after="desulfation",
            first_stage=assessment(FirstStageState.VOLTAGE_UNSTABLE),
        )
        self.assertEqual(result.severity, TransitionAuditSeverity.SAFETY)

    def test_stuck_plateau_is_compatible_evidence_but_not_proof_of_recipe_need(self):
        result = audit_legacy_transition(
            stage_before="Main Charge",
            stage_after="Десульфатация",
            first_stage=assessment(FirstStageState.STUCK_PLATEAU),
        )
        self.assertEqual(result.severity, TransitionAuditSeverity.INFO)
        self.assertIn("chemistry/intent/condition", result.reason)


if __name__ == "__main__":
    unittest.main()
