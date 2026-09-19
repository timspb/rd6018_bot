import unittest
from pathlib import Path


DOC = Path(__file__).parents[1] / "docs" / "RD6018_LIVE_SHADOW_DECISION_BRIDGE_REPORT.md"


class Workstream92LiveShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_live_snapshot_fields(self):
        for value in ("Baic72", "MIX", "17.10 V", "3.49 A", "protection", "lease"):
            self.assertIn(value, self.text)

    def test_shadow_decision_and_parity(self):
        for value in ("manual:Baic72", "17.5 V / 3.5 A", "ALLOW", "MATCH"):
            self.assertIn(value, self.text)

    def test_legacy_identity_is_unknown(self):
        self.assertIn("PARTIAL_LEGACY_IDENTITY_UNKNOWN", self.text)
        self.assertIn("no reconstruction", self.text)

    def test_fail_closed_rules(self):
        for value in ("unknown", "safety `deny`", "identity mismatch"):
            self.assertIn(value, self.text.lower())

    def test_no_side_effects(self):
        for value in ("no HA service call", "physical execution", "did not influence V2"):
            self.assertIn(value, self.text)

    def test_not_a_cutover(self):
        self.assertIn("does not authorize Canary", self.text)


if __name__ == "__main__":
    unittest.main()
