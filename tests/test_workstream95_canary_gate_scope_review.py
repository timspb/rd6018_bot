import unittest
from pathlib import Path


DOC = Path(__file__).parents[1] / "docs" / "RD6018_CANARY_GATE_SCOPE_REVIEW.md"


class Workstream95ScopeReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_observe_only_is_ready(self):
        self.assertIn("OBSERVE_ONLY_READY", self.text)
        for requirement in ("telemetry freshness", "source availability", "parity visibility"):
            self.assertIn(requirement, self.text)

    def test_canary_requirements_are_separate(self):
        for requirement in ("execution approval", "lease ownership", "physical adapter readiness"):
            self.assertIn(requirement, self.text)
        self.assertIn("APPROVED_CANARY", self.text)

    def test_no_false_execution_readiness(self):
        self.assertIn("не означает `APPROVED_CANARY`", self.text)
        self.assertIn("V2 остаётся production и physical owner", self.text)

    def test_unknown_and_parity_rules(self):
        self.assertIn("`UNKNOWN`", self.text)
        self.assertIn("DIVERGENCE", self.text)


if __name__ == "__main__":
    unittest.main()
