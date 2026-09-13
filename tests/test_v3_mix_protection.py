import unittest

from external_temp_integrity import ExternalTempIntegrityMonitor, ExternalTempIntegrityPolicy
from runtime.charge import Measurements
from runtime.charge.strategy import (
    CCMixExitConfig,
    CVMixExitConfig,
    MixCurrentContainmentState,
    MixPolicy,
    MixPolicyConfig,
    MixTemperatureIntegrityPolicy,
    emergency_stop_reset_intent,
    post_mix_reset_intent,
)


def _temp(value: float, second: int) -> dict:
    stamp = f"2026-01-01T00:00:{second:02d}+00:00"
    return {"temp_ext": value, "_meta": {"temp_ext": {"last_reported": stamp}}}


class V3MixProtectionTests(unittest.TestCase):
    def _mix(self) -> MixPolicy:
        cc = CCMixExitConfig(16.5, 0.03, 2, 7200.0, 16.5, 2.0)
        cv = CVMixExitConfig(0.4, 0.1, 2, 7200.0, 16.5, 2.0)
        return MixPolicy(MixPolicyConfig(10000.0, cc, cv))

    def test_containment_state_is_explicit_and_not_timer_data(self):
        mix = self._mix()
        self.assertIsInstance(mix.cv.state.containment, MixCurrentContainmentState)
        self.assertFalse(mix.cv.state.containment.enabled)

        for t, current in ((0.0, 0.4), (1.0, 0.5), (2.0, 0.5), (1800.0, 0.8)):
            intent = mix.evaluate("CV", Measurements(16.5, current, 25.0, t))
        self.assertTrue(mix.cv.state.containment.enabled)
        self.assertEqual(1800.0, mix.cv.state.containment.activated_at)
        self.assertAlmostEqual(0.9, mix.cv.state.containment.fixed_limit)
        self.assertAlmostEqual(0.9, intent.target_current)

    def test_containment_recalculation_is_cadenced_and_never_increases(self):
        mix = self._mix()
        for t, current in ((0.0, 0.4), (1.0, 0.5), (2.0, 0.5), (1800.0, 0.8)):
            mix.evaluate("CV", Measurements(16.5, current, 25.0, t))
        state = mix.cv.state.containment
        self.assertEqual(1800.0, state.last_recalculation)
        mix.evaluate("CV", Measurements(16.5, 1.8, 25.0, 1801.0))
        self.assertEqual(1800.0, state.last_recalculation)
        mix.evaluate("CV", Measurements(16.5, 1.8, 25.0, 2400.0))
        self.assertEqual(2400.0, state.last_recalculation)
        self.assertAlmostEqual(0.9, state.fixed_limit)
        self.assertEqual(0, state.reduction_count)

    def test_post_mix_and_emergency_reset_intents_are_non_actuating(self):
        normal = post_mix_reset_intent(17.5, 12.0, reason="MIX_FINISH")
        emergency = emergency_stop_reset_intent(17.5, 12.0, reason="MIX_SENSOR_FAULT")
        self.assertEqual("MIX", normal.source_phase)
        self.assertEqual("MIX_EMERGENCY_STOP", emergency.source_phase)
        self.assertEqual((17.5, 12.0), (normal.target_ovp, normal.target_ocp))

    def test_mix_temperature_policy_latches_impossible_drop(self):
        monitor = ExternalTempIntegrityMonitor(
            ExternalTempIntegrityPolicy(consecutive_samples=2, max_step_c=5.0), fault_file=""
        )
        policy = MixTemperatureIntegrityPolicy(monitor)
        self.assertFalse(policy.evaluate(_temp(29.0, 0)).stop)
        self.assertFalse(policy.evaluate(_temp(30.0, 1)).stop)
        self.assertFalse(policy.evaluate(_temp(31.0, 2)).stop)
        self.assertFalse(policy.evaluate(_temp(32.0, 3)).stop)
        self.assertFalse(policy.evaluate(_temp(33.0, 4)).stop)
        self.assertFalse(policy.evaluate(_temp(15.0, 5)).stop)
        decision = policy.evaluate(_temp(25.0, 6))
        self.assertTrue(decision.stop)
        self.assertTrue(decision.diagnostic_latched)


if __name__ == "__main__":
    unittest.main()
