import unittest
from pathlib import Path


DOC = Path(__file__).parents[1] / "docs" / "RD6018_V2_V3_SHADOW_DECISION_BRIDGE_MODEL.md"


class Workstream91ShadowBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_input_contract(self):
        for field in ("v2_live_state", "telemetry_snapshot", "active_program", "current_phase", "safety_state"):
            self.assertIn(field, self.text)

    def test_v3_shadow_output(self):
        for field in ("selected_program", "phase_decision", "target_voltage", "target_current", "safety_decision", "execution_intent"):
            self.assertIn(field, self.text)

    def test_comparison_categories(self):
        for category in ("MATCH", "EXPECTED_DIFFERENCE", "DIVERGENCE", "UNKNOWN"):
            self.assertIn(category, self.text)

    def test_fail_closed_inputs(self):
        for condition in ("missing telemetry", "stale V2 state", "identity mismatch"):
            self.assertIn(condition, self.text)
        self.assertIn("safety `DENY`", self.text)

    def test_no_side_effects(self):
        for phrase in ("HA/ESPHome/Modbus writes", "execution dispatcher calls", "lease mutation", "physical calls"):
            self.assertIn(phrase, self.text)

    def test_v2_is_not_influenced(self):
        self.assertIn("Ни один результат V3 не влияет на V2", self.text)


if __name__ == "__main__":
    unittest.main()
