import unittest
from pathlib import Path


DOC = Path(__file__).parents[1] / "docs" / "RD6018_V3_CANARY_REVIEW_READINESS.md"


class Workstream93CanaryReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_status_is_fail_closed(self):
        self.assertIn("V3_CANARY_REVIEW_BLOCKED", self.text)
        self.assertIn("**Conclusion:** `V3_CANARY_REVIEW_READY` is not", self.text)

    def test_required_gates_are_reviewed(self):
        for gate in ("dependency direction", "ownership/authority", "safety fail-closed", "live shadow decision", "audit trace", "recovery/rollback", "external parity", "approval"):
            self.assertIn(gate, self.text)

    def test_blockers_are_explicit(self):
        for blocker in ("CR-001", "CR-002", "CR-003", "CR-004", "CR-005"):
            self.assertIn(blocker, self.text)

    def test_live_match_is_qualified(self):
        self.assertIn("Baic72/Manual/MIX", self.text)
        self.assertIn("17.10 V", self.text)
        self.assertIn("session_id`/`trace_id`", self.text)

    def test_no_side_effects(self):
        for phrase in ("no HA/ESPHome/RD/Modbus calls", "no START/STOP/PAUSE", "no lease operation", "no ownership transfer"):
            self.assertIn(phrase, self.text)

    def test_next_workstreams_exist(self):
        for workstream in ("WS93.1", "WS93.2", "WS93.3", "WS93.4"):
            self.assertIn(workstream, self.text)


if __name__ == "__main__":
    unittest.main()
