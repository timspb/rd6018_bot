import unittest
from pathlib import Path


DOC = Path(__file__).parents[1] / "docs" / "RD6018_CONTROL_EVENT_AUDIT_CHAIN_MODEL.md"


class Workstream89AuditChainDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_common_identity_envelope(self):
        for field in ("event_id", "session_id", "trace_id", "decision_id", "intent_id", "timestamp"):
            self.assertIn(field, self.text)

    def test_all_control_chains_are_present(self):
        for name in ("### START", "### STOP", "### PAUSE", "### EMERGENCY"):
            self.assertIn(name, self.text)

    def test_physical_confirmation_is_not_synthesized(self):
        self.assertIn("не означает Output ON", self.text)
        self.assertIn("не утверждает успешный physical result без readback", self.text)
        self.assertIn("FAILED` или `UNKNOWN", self.text)

    def test_replay_and_duplicate_rules(self):
        self.assertIn("append-only", self.text)
        self.assertIn("повторный `event_id`", self.text)
        self.assertIn("Replay возвращает фактический порядок", self.text)

    def test_pause_continuity_and_emergency_recovery(self):
        self.assertIn("Session identity", self.text)
        self.assertIn("RecoveryState", self.text)
        self.assertIn("fail-closed", self.text)

    def test_no_runtime_integration(self):
        for phrase in ("physical executor", "production", "control path"):
            self.assertIn(phrase, self.text)


if __name__ == "__main__":
    unittest.main()
