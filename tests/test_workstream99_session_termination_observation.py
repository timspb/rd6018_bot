import unittest
from pathlib import Path


DOC = Path(__file__).parents[1] / "docs" / "RD6018_SESSION_TERMINATION_EVIDENCE_OBSERVATION.md"


class Workstream99TerminationObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_partial_status(self):
        self.assertIn("PARTIAL_OBSERVATION", self.text)

    def test_mix_continuation(self):
        for value in ("phase: MIX", "V2 lifecycle: ACTIVE", "17.5 V / 3.5 A", "MATCH"):
            self.assertIn(value, self.text)

    def test_transitions_are_not_fabricated(self):
        for transition in ("MIX -> HOLD", "HOLD -> DONE", "DONE -> idle"):
            self.assertIn(transition, self.text)
        self.assertIn("NOT_OBSERVED", self.text)
        self.assertIn("No synthetic completion", self.text)

    def test_output_off_is_not_done(self):
        self.assertIn("`Output OFF` не считается `DONE`", self.text)
        self.assertIn("output OFF alone is insufficient", self.text)

    def test_no_control(self):
        for value in ("STOP", "lease operation", "physical command"):
            self.assertIn(value, self.text)


if __name__ == "__main__":
    unittest.main()
