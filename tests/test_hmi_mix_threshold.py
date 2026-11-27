"""MIX reversal hint is informative and preserves controller precision."""
import unittest
from runtime.ui.components.hmi_mix_threshold import cv_delta_status, cc_delta_status

class MixThresholdHintTests(unittest.TestCase):
    def test_actual_efb_example_preserves_subcentiamp_target(self):
        label = cv_delta_status(1.85, 0.04, 0.555)
        self.assertIn("Imin 1.85 A", label)
        self.assertIn("I≥2.405 A", label)
        self.assertNotIn("I≥2.40 A", label)
    def test_cc_means_drop_from_voltage_max(self):
        self.assertIn("U≤16.450 V", cc_delta_status(16.55, 0.03, 0.10))
