import unittest
from pathlib import Path


DOC = Path(__file__).parents[1] / "docs" / "RD6018_CONTROLLED_LIVE_TEST_PROGRAM_REPORT.md"


class Workstream101ControlledLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_stopped_status(self):
        self.assertIn("STOPPED_WITH_REASON", self.text)
        self.assertIn("stale telemetry", self.text)

    def test_preflight_limits(self):
        for value in ("12.73 V", "13.0 V", "0.5 A", "<= 0.9 A", "protection: code 0"):
            self.assertIn(value, self.text)

    def test_fail_closed_result(self):
        self.assertIn("3846.6 s", self.text)
        self.assertIn("enable result: disabled", self.text)
        self.assertIn("Output ON", self.text)
        self.assertIn("physical execution occurred", self.text)

    def test_unrun_tests_are_explicit(self):
        for test_name in ("START/STOP boundary", "voltage/current change", "CC/CV transition", "MIX/HOLD", "STOP path"):
            self.assertIn(test_name, self.text)
        self.assertIn("NOT_RUN", self.text)

    def test_no_synthetic_lifecycle(self):
        self.assertIn("no real", self.text)
        self.assertIn("was synthesized", self.text)


if __name__ == "__main__":
    unittest.main()
