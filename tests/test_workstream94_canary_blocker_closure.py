import unittest
from pathlib import Path

from application.canary_approval import CanaryApproval, CanaryApprovalMode


DOC = Path(__file__).parents[1] / "docs" / "RD6018_CANARY_BLOCKER_CLOSURE_REPORT.md"


class Workstream94CanaryClosureTests(unittest.TestCase):
    def test_approval_contract(self):
        approval = CanaryApproval(
            "approval-1", CanaryApprovalMode.SHADOW_DECISION, "shadow",
            {"physical_execution": "disabled"}, 10.0, 20.0,
            ("safety conflict", "expiry"),
        )
        self.assertTrue(approval.valid_at(15.0))
        self.assertFalse(approval.revoke().valid_at(15.0))

    def test_approval_requires_rollback(self):
        with self.assertRaises(ValueError):
            CanaryApproval("approval-1", CanaryApprovalMode.OBSERVE_ONLY, "scope", {}, 1.0, 2.0, ())

    def test_report_has_all_blockers(self):
        text = DOC.read_text(encoding="utf-8")
        for blocker in ("CB-APPROVAL", "CB-SAFETY-FRESHNESS", "CB-SOURCE-PARITY", "CB-LEGACY-IDENTITY", "CB-CONFIG-NAMESPACE"):
            self.assertIn(blocker, text)

    def test_legacy_policy_is_fail_closed(self):
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("Legacy sessions are forbidden as Canary decision inputs", text)
        self.assertIn("No synthetic identity", text)

    def test_source_authority_is_explicit(self):
        text = DOC.read_text(encoding="utf-8")
        for source in ("RD readback", "ESPHome", "HA", "V2 state"):
            self.assertIn(source, text)

    def test_no_activation(self):
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("BLOCKED_WITH_REASONS", text)
        self.assertIn("No START, STOP, PAUSE", text)

    def test_fresh_read_only_snapshot_is_recorded(self):
        text = DOC.read_text(encoding="utf-8")
        for value in ("Output: OFF", "Battery voltage: 12.73 V", "Protection: code 0", "13.0 V / 0.4 A"):
            self.assertIn(value, text)
        self.assertIn("does not close `CB-SAFETY-FRESHNESS`", text)


if __name__ == "__main__":
    unittest.main()
