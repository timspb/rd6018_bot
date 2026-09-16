import unittest

from runtime.diagnostics import (
    DiagnosticAuthority, DiagnosticDecision, SafetyEvidence,
    combine_safety_evidence, safety_evidence_from_diagnostic,
)
from runtime.safety import SafetyEngine, SafetyLimits, SafetyParityComparator


class V3SafetyEvidencePipelineTests(unittest.TestCase):
    def test_normal_evidence_is_allowed(self):
        evidence = safety_evidence_from_diagnostic(
            DiagnosticDecision(DiagnosticAuthority.ALLOW), timestamp=1.0,
        )
        decision = SafetyEngine(SafetyLimits(20.0, 12.0)).evaluate_evidence((evidence,))
        self.assertTrue(decision.allowed)

    def test_highest_authority_wins_and_denies(self):
        allowed = SafetyEvidence(True, DiagnosticAuthority.ALLOW, "ok", "telemetry", 1.0)
        blocked = SafetyEvidence(False, DiagnosticAuthority.BLOCK_AUTOMATIC_HV, "cell fault suspected", "diagnostics", 2.0, ("cell",), "error", 0.9)
        combined = combine_safety_evidence((allowed, blocked))
        decision = SafetyEngine(SafetyLimits(20.0, 12.0)).evaluate_evidence((allowed, blocked))
        self.assertEqual(combined.authority, DiagnosticAuthority.BLOCK_AUTOMATIC_HV)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.authority, DiagnosticAuthority.BLOCK_AUTOMATIC_HV)

    def test_hard_stop_is_critical_and_no_output_is_created(self):
        evidence = SafetyEvidence(False, DiagnosticAuthority.HARD_STOP, "confirmed fault", "diagnostics", 1.0, (), "critical")
        decision = SafetyEngine(SafetyLimits(20.0, 12.0)).evaluate_evidence((evidence,))
        self.assertTrue(decision.shutdown_required)
        self.assertEqual(decision.violations[0].severity, "critical")
        self.assertIsNone(decision.intent)

    def test_parity_reports_mismatch_without_fixing_it(self):
        result = SafetyParityComparator.compare({"allowed": True}, {"allowed": False})
        self.assertEqual(result.status, "MISMATCH")
        self.assertEqual(result.fields, ("allowed",))


if __name__ == "__main__":
    unittest.main()
