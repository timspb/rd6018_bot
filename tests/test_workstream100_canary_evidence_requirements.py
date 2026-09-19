import unittest
from pathlib import Path


DOC = Path(__file__).parents[1] / "docs" / "RD6018_CANARY_EVIDENCE_REQUIREMENTS_MODEL.md"


class Workstream100EvidenceRequirementsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_ready_status(self):
        self.assertIn("CANARY_EVIDENCE_MODEL_READY", self.text)

    def test_three_modes(self):
        for mode in ("OBSERVE_ONLY", "SHADOW_DECISION", "APPROVED_CANARY"):
            self.assertIn(mode, self.text)

    def test_shadow_phase_and_cycle_rules(self):
        for phase in ("PREP", "MAIN", "MIX", "HOLD", "DONE"):
            self.assertIn(phase, self.text)
        self.assertIn("один полный decision-consistent observation cycle", self.text)

    def test_canary_gates(self):
        for gate in ("approval_id", "lease evidence", "session_id", "trace_id", "rollback procedure", "readback verification"):
            self.assertIn(gate, self.text)

    def test_blocker_classification(self):
        self.assertIn("### BLOCKER", self.text)
        self.assertIn("### NICE_TO_HAVE", self.text)
        self.assertIn("synthetic/fake lifecycle evidence", self.text)

    def test_no_automatic_transition(self):
        self.assertIn("явной gate evaluation", self.text)
        self.assertIn("unit tests", self.text)


if __name__ == "__main__":
    unittest.main()
