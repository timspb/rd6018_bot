import unittest
from pathlib import Path


class Workstream104ControlledTestSuiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (
            Path(__file__).parents[1]
            / "docs"
            / "RD6018_CONTROLLED_TEST_SUITE_REPORT.md"
        ).read_text(encoding="utf-8")

    def test_suite_and_all_physical_cases_completed(self):
        self.assertIn("CONTROLLED_TEST_SUITE_COMPLETE", self.text)
        for test_name in (
            "START/STOP BASIC",
            "LOW CURRENT CHARGE",
            "CURRENT CHANGE WHILE ON",
            "VOLTAGE CHANGE WHILE ON",
            "CC/CV TRANSITION PREPARATION",
        ):
            self.assertIn(test_name, self.text)
        self.assertEqual(self.text.count("| PASS |"), 5)

    def test_limits_and_minimum_on_time_are_evidenced(self):
        self.assertIn("maximum current: `0.9 A`", self.text)
        self.assertIn("10.126 s", self.text)
        self.assertIn("10.195 s", self.text)
        self.assertIn("ранний STOP не выполнялся", self.text)
        self.assertIn("current=0.0 A", self.text)

    def test_fail_closed_paths_and_identity_gap_are_explicit(self):
        for marker in ("stale Modbus age → `DENY`", "protection code 1 → `DENY`", "invalid Output State Code → `DENY`"):
            self.assertIn(marker, self.text)
        self.assertIn("UNKNOWN_LEGACY_NO_IDENTITY", self.text)
        self.assertIn("без synthetic events", self.text)


if __name__ == "__main__":
    unittest.main()
