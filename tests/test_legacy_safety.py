import unittest

from config import MAX_VOLTAGE
from legacy_safety import (
    clamp_legacy_target_voltage,
    main_timeout_decision,
    mix_timeout_decision,
    mix_timeout_hours,
)


class LegacySafetyInvariantTests(unittest.TestCase):
    def test_temperature_compensated_target_is_clamped_after_compensation(self):
        self.assertEqual(clamp_legacy_target_voltage(16.77), MAX_VOLTAGE)
        self.assertEqual(clamp_legacy_target_voltage(17.10), MAX_VOLTAGE)
        self.assertEqual(clamp_legacy_target_voltage(14.82), 14.82)

    def test_main_timeout_is_always_a_stop_decision(self):
        self.assertFalse(main_timeout_decision(elapsed_hours=71.99, max_hours=72).stop)
        decision = main_timeout_decision(elapsed_hours=72.01, max_hours=72)
        self.assertTrue(decision.stop)
        self.assertIn("hard safety timeout", decision.reason)

    def test_mix_profile_limits_are_explicit(self):
        self.assertEqual(mix_timeout_hours("EFB"), 20.0)
        self.assertEqual(mix_timeout_hours("Ca/Ca"), 20.0)
        self.assertEqual(mix_timeout_hours("AGM"), 10.0)
        self.assertIsNone(mix_timeout_hours("Custom"))

    def test_mix_timeout_cannot_be_disabled_by_external_stop_policy(self):
        # There intentionally is no manual_off/user-policy parameter here.
        self.assertTrue(
            mix_timeout_decision(
                profile="EFB",
                elapsed_hours=20.01,
                finish_timer_active=False,
            ).stop
        )

    def test_active_delta_finish_timer_owns_mix_completion(self):
        self.assertFalse(
            mix_timeout_decision(
                profile="AGM",
                elapsed_hours=12.0,
                finish_timer_active=True,
            ).stop
        )


if __name__ == "__main__":
    unittest.main()
