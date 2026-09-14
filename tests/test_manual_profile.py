import tempfile
import unittest
from pathlib import Path

from runtime.charge.profiles.manual import ManualChargeProfile, load_manual_profile, save_manual_profile


class ManualProfileTests(unittest.TestCase):
    def test_repository_profile_has_separate_main_and_mix_fields(self):
        profile = load_manual_profile(Path(__file__).parents[1] / "config" / "charge" / "manual.yaml")
        self.assertEqual(profile.main.voltage_v, 14.7)
        self.assertEqual(profile.main.minimum_current_a, 0.30)
        self.assertEqual(profile.mix.voltage_v, 16.5)
        self.assertEqual(profile.mix.delta_current_a, 0.03)
        self.assertEqual(profile.mix.hold_hours, 2)

    def test_main_cannot_contain_delta(self):
        raw = {
            "main": {"voltage_v": 14.7, "current_a": 5, "minimum_current_a": .3, "hold_hours": 0, "delta_current_a": .03},
            "mix": {"voltage_v": 16.5, "current_a": 1.5, "delta_voltage_v": .03, "delta_current_a": .03, "hold_hours": 2},
        }
        with self.assertRaisesRegex(ValueError, "MAIN must not define delta"):
            ManualChargeProfile.from_mapping(raw)

    def test_mix_requires_both_mode_deltas(self):
        raw = {
            "main": {"voltage_v": 14.7, "current_a": 5, "minimum_current_a": .3, "hold_hours": 0},
            "mix": {"voltage_v": 16.5, "current_a": 1.5, "delta_current_a": .03, "hold_hours": 2},
        }
        with self.assertRaisesRegex(ValueError, "both delta"):
            ManualChargeProfile.from_mapping(raw)

    def test_battery_override_is_persisted_separately(self):
        profile = load_manual_profile(Path(__file__).parents[1] / "config" / "charge" / "manual.yaml")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual.yaml"
            save_manual_profile(profile, path)
            custom = ManualChargeProfile(
                main=type(profile.main)(14.8, 4.0, 1.0, minimum_current_a=0.2, confirmation_count=2),
                mix=type(profile.mix)(16.4, 1.2, 2.5, delta_voltage_v=0.04, delta_current_a=0.04),
                profile_id="Baic72",
            )
            save_manual_profile(custom, path, battery_id="Baic72")
            restored = load_manual_profile(path, battery_id="Baic72")
            default = load_manual_profile(path)
            self.assertEqual(restored.main.hold_hours, 1.0)
            self.assertEqual(restored.mix.delta_current_a, 0.04)
            self.assertEqual(default.main.hold_hours, profile.main.hold_hours)
