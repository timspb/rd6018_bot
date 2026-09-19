import unittest
from pathlib import Path


DOC = Path(__file__).parents[1] / "docs" / "RD6018_LIVE_OBSERVE_ONLY_VALIDATION_REPORT.md"


class Workstream96LiveObserveOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_validated_status_and_sources(self):
        self.assertIn("LIVE_OBSERVE_ONLY_VALIDATED", self.text)
        for source in ("HA", "RD via HA", "ESPHome", "V2 lifecycle"):
            self.assertIn(source, self.text)

    def test_live_values_are_recorded(self):
        for value in ("Output OFF", "12.73 V", "13.0 V / 0.4 A", "code 0", "Baic72/Manual/MIX/ACTIVE"):
            self.assertIn(value, self.text)

    def test_shadow_fields_and_parity(self):
        for value in ("program", "phase", "targets", "safety", "intent", "MATCH", "UNKNOWN"):
            self.assertIn(value, self.text)

    def test_ui_layers_are_separated(self):
        for value in ("Charge card", "Graph", "Log", "Diagnostics", "Control surface"):
            self.assertIn(value, self.text)

    def test_no_side_effects(self):
        for value in ("No HA", "No HA", "setpoint write", "lease operation", "physical adapter call"):
            self.assertIn(value, self.text)

    def test_not_canary_execution(self):
        self.assertIn("does not imply", self.text)
        self.assertIn("V2 remained the sole control owner", self.text)


if __name__ == "__main__":
    unittest.main()
