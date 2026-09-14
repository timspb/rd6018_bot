import unittest
from pathlib import Path

from runtime.charge.profiles.manual import ManualChargeProfile, load_manual_profile


class ManualProfileTests(unittest.TestCase):
    def test_repository_profile_has_separate_main_and_mix_fields(self):
        profile = load_manual_profile(Path(__file__).parents[1] / "config" / "charge" / "manual.yaml")
        self.assertEqual(profile.main.voltage_v, 14.7)
        self.assertEqual(profile.main.minimum_current_a, 0.30)
        self.assertEqual(profile.mix.voltage_v, 16.5)
        self.assertEqual(profile.mix.delta_current_a, 0.03)
        self.assertEqual(profile.mix.hold_seconds, 7200)

    def test_main_cannot_contain_delta(self):
        raw = {
            "main": {"voltage_v": 14.7, "current_a": 5, "minimum_current_a": .3, "hold_seconds": 0, "delta_current_a": .03},
            "mix": {"voltage_v": 16.5, "current_a": 1.5, "delta_voltage_v": .03, "delta_current_a": .03, "hold_seconds": 7200},
        }
        with self.assertRaisesRegex(ValueError, "MAIN must not define delta"):
            ManualChargeProfile.from_mapping(raw)

    def test_mix_requires_both_mode_deltas(self):
        raw = {
            "main": {"voltage_v": 14.7, "current_a": 5, "minimum_current_a": .3, "hold_seconds": 0},
            "mix": {"voltage_v": 16.5, "current_a": 1.5, "delta_current_a": .03, "hold_seconds": 7200},
        }
        with self.assertRaisesRegex(ValueError, "both delta"):
            ManualChargeProfile.from_mapping(raw)
