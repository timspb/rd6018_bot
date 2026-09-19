import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class Workstream109To112FinalValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = (ROOT / "docs" / "RD6018_FINAL_V3_CONTROLLED_VALIDATION_REPORT.md").read_text(encoding="utf-8")

    def test_report_is_conservative_about_final_status(self):
        self.assertIn("BLOCKED_WITH_REASONS", self.report)
        self.assertIn("PARTIAL", self.report)
        self.assertIn("UNKNOWN", self.report)

    def test_controlled_limits_are_recorded(self):
        self.assertIn("<= 0.9 A", self.report)
        self.assertIn(">= 10 s", self.report)
        self.assertIn("ранний STOP не выполнялся", self.report)

    def test_prior_control_and_identity_evidence_is_referenced(self):
        self.assertIn("WS106", self.report)
        self.assertIn("WS104", self.report)
        self.assertIn("intent_id", self.report)
        self.assertIn("session_id", self.report)
        self.assertIn("trace_id", self.report)

    def test_safety_and_lease_fail_closed_cases_are_present(self):
        for marker in (
            "stale Modbus -> `DENY`",
            "invalid readback -> `DENY`",
            "protection fault simulation -> `DENY`",
            "missing evidence -> `DENY`",
            "fake STOP и fake DONE не создаются",
        ):
            self.assertIn(marker, self.report)

    def test_full_lifecycle_gap_is_not_fabricated(self):
        self.assertIn("## E — Full lifecycle observation", self.report)
        self.assertIn("full natural chain not evidenced", self.report)
        self.assertIn("Output OFF", self.report)
        self.assertIn("UNKNOWN_LEGACY_NO_IDENTITY", self.report)
        self.assertIn("synthetic", self.report)
        self.assertIn("V2 lifecycle event", self.report)

    def test_ui_and_recovery_acceptance_are_separate(self):
        self.assertIn("F — Operator UI acceptance", self.report)
        self.assertIn("G — Recovery", self.report)
        self.assertIn("charge card", self.report)
        self.assertIn("ambiguous legacy snapshot", self.report)

    def test_no_ownership_or_direct_execution_claim(self):
        self.assertIn("ownership", self.report)
        self.assertIn("V3 direct execution", self.report)
        self.assertIn("fake identity/events", self.report)


if __name__ == "__main__":
    unittest.main()
