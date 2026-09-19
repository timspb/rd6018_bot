import unittest


class Workstream103ControlledStartVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pathlib import Path

        cls.text = (
            Path(__file__).parents[1]
            / "docs"
            / "RD6018_CONTROLLED_START_VERIFICATION_REPORT.md"
        ).read_text(encoding="utf-8")

    def test_verified_status_and_safety_limits(self):
        self.assertIn("CONTROLLED_START_VERIFIED", self.text)
        self.assertIn("12.73 V", self.text)
        self.assertIn("13.0 V", self.text)
        self.assertIn("0.4 A", self.text)
        self.assertIn("0.39 A", self.text)
        self.assertIn("0 / normal", self.text)

    def test_output_transition_and_minimum_hold(self):
        self.assertIn("Output State Code V2: `1 / ON`", self.text)
        self.assertIn("final Output State Code V2: `0 / OFF`", self.text)
        self.assertIn("10.139 s", self.text)
        self.assertIn(">= 10 s", self.text)
        self.assertIn("ранний STOP: `false`", self.text)

    def test_identity_is_not_synthesized(self):
        for field in ("session_id", "trace_id", "decision_id"):
            self.assertIn(field, self.text)
        self.assertIn("UNKNOWN", self.text)
        self.assertIn("не реконструировались", self.text)


if __name__ == "__main__":
    unittest.main()
