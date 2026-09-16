import unittest

from runtime.diagnostics import (
    BatteryCondition, BatteryDiagnosticEvidence, BatteryDiagnosticsEngine,
    DiagnosticAuthority, DiagnosticEvidenceItem, DiagnosticHypothesis,
    DiagnosticLevel, HypothesisAssessment, LegacyDiagnosticAdapter,
)


class V3BatteryDiagnosticsTests(unittest.TestCase):
    def test_evidence_and_hypothesis_are_data_only(self):
        item = DiagnosticEvidenceItem(
            "cell_fault", "multi_signal", 100.0, "test", DiagnosticLevel.HIGH,
        )
        hypothesis = HypothesisAssessment(
            DiagnosticHypothesis.CELL_FAULT, DiagnosticLevel.HIGH, 0.95, ("cell_fault",),
        )
        self.assertEqual(item.source, "test")
        self.assertEqual(hypothesis.evidence_refs, ("cell_fault",))

    def test_explicit_confirmed_fault_is_hard_stop_evidence(self):
        report = BatteryDiagnosticsEngine().evaluate(
            BatteryDiagnosticEvidence(
                cell_fault_confirmed=True,
                evidence_ids=("independent_cell_check",),
                items=(DiagnosticEvidenceItem(
                    "cell_fault", "confirmed", 100.0, "external", DiagnosticLevel.HIGH,
                ),),
            )
        )
        self.assertEqual(report.authority.authority, DiagnosticAuthority.HARD_STOP)
        self.assertEqual(report.condition, BatteryCondition.DEGRADED)

    def test_legacy_assessment_maps_without_running_legacy_code(self):
        report = LegacyDiagnosticAdapter.to_report({
            "authority": "block_automatic_hv",
            "authority_reasons": ("multi_signal",),
            "hypotheses": {
                "cell_fault": {"score": 80, "level": "high", "reasons": ("rested_ocv",)},
            },
        })
        self.assertEqual(report.authority.authority, DiagnosticAuthority.BLOCK_AUTOMATIC_HV)
        self.assertEqual(report.hypotheses[0].hypothesis, DiagnosticHypothesis.CELL_FAULT)

    def test_invalid_hypothesis_confidence_rejected(self):
        with self.assertRaises(ValueError):
            HypothesisAssessment(DiagnosticHypothesis.CELL_FAULT, DiagnosticLevel.HIGH, 1.1)


if __name__ == "__main__":
    unittest.main()
