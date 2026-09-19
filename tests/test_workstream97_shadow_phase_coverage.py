import unittest
from pathlib import Path


DOC = Path(__file__).parents[1] / "docs" / "RD6018_SHADOW_PHASE_COVERAGE_EXPANSION.md"


class Workstream97ShadowCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_partial_status_is_explicit(self):
        self.assertIn("PARTIAL_OBSERVATION", self.text)

    def test_all_required_phases_are_in_matrix(self):
        for phase in ("PREP", "MAIN", "MIX", "HOLD", "SAFE_WAIT", "DONE"):
            self.assertIn(f"| {phase} |", self.text)

    def test_real_mix_evidence_is_recorded(self):
        for value in ("manual:Baic72", "17.5 V / 3.5 A", "17.10 V / 3.49 A", "MATCH"):
            self.assertIn(value, self.text)

    def test_unobserved_phases_are_not_reconstructed(self):
        self.assertIn("No real correlated evidence", self.text)
        self.assertIn("No phase transitions were inferred", self.text)
        self.assertIn("NOT_OBSERVED", self.text)

    def test_no_side_effects(self):
        for value in ("No command", "lease mutation", "physical", "ownership change"):
            self.assertIn(value, self.text)


if __name__ == "__main__":
    unittest.main()
