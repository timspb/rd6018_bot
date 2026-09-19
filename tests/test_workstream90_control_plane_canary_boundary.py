import unittest
from pathlib import Path


DOC = Path(__file__).parents[1] / "docs" / "RD6018_V3_CONTROL_PLANE_CANARY_BOUNDARY_MODEL.md"


class Workstream90BoundaryDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_canary_modes(self):
        for mode in ("OBSERVE_ONLY", "SHADOW_DECISION", "APPROVED_CANARY", "ROLLBACK"):
            self.assertIn(mode, self.text)

    def test_v2_remains_physical_owner(self):
        self.assertIn("V2 Physical Owner", self.text)
        self.assertIn("one physical execution owner: V2", self.text)
        self.assertIn("V2 continues as sole physical owner", self.text)

    def test_v3_decision_contract(self):
        for field in ("program_id", "session_id", "trace_id", "phase", "targets", "safety_context", "execution_intent"):
            self.assertIn(field, self.text)
        for result in ("accepted", "rejected", "physical_result", "verification"):
            self.assertIn(result, self.text)

    def test_failure_rules(self):
        for phrase in ("V3 unavailable", "DIVERGENCE", "verification failed", "session identity mismatch"):
            self.assertIn(phrase, self.text)

    def test_no_direct_physical_boundary(self):
        for phrase in ("direct HA calls", "direct ESPHome calls", "direct Modbus", "no V3 physical imports or calls"):
            self.assertIn(phrase, self.text)

    def test_no_automatic_rollback_execution(self):
        self.assertIn("no automatic rollback execution", self.text)
        self.assertIn("explicit approval required", self.text)


if __name__ == "__main__":
    unittest.main()
