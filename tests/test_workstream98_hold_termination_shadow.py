import unittest
from pathlib import Path


DOC = Path(__file__).parents[1] / "docs" / "RD6018_HOLD_TERMINATION_SHADOW_OBSERVATION.md"


class Workstream98HoldTerminationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_partial_status(self):
        self.assertIn("PARTIAL_OBSERVATION", self.text)

    def test_mix_entry(self):
        for value in ("V2 phase: MIX", "V3 phase: MIX", "17.5 V / 3.5 A", "MATCH"):
            self.assertIn(value, self.text)

    def test_hold_is_not_inferred(self):
        self.assertIn("нет реального `HoldStarted`", self.text)
        self.assertIn("hold condition", self.text)
        self.assertIn("не реконструировались", self.text)

    def test_off_is_not_done(self):
        self.assertIn("Output OFF/zero-output", self.text)
        self.assertIn("не трактуется как `DONE`", self.text)
        self.assertIn("UNKNOWN", self.text)

    def test_no_side_effects(self):
        for value in ("commands", "writes", "lease actions", "physical execution"):
            self.assertIn(value, self.text)


if __name__ == "__main__":
    unittest.main()
