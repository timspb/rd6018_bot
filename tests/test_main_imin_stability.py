"""Regression for a sustained MAIN Imin (distinct from MIX Delta-I)."""
import unittest

from signal_analyzer import SignalAnalyzer, SignalSample
from application.production_session_extensions import runtime_signal_snapshot


def sample(t, i, cv=True):
    return SignalSample(t, 14.85, i, 23.0, is_cv=cv, is_cc=not cv)


class MainIminStabilityTests(unittest.TestCase):
    def analyzer(self):
        a = SignalAnalyzer()
        a.reset_stage("Main Charge", target_voltage_v=14.84)
        return a

    def test_sustained_rise_clears_hold_until_minimum_returns(self):
        a = self.analyzer()
        a.observe(sample(0, 0.22))
        self.assertEqual(a.observe(sample(30, 0.22)).metrics.main_stable_hold_s, 30)
        self.assertEqual(a.observe(sample(60, 0.23)).metrics.main_stable_hold_s, 0)
        high = a.observe(sample(90, 0.23)).metrics
        self.assertEqual(high.current_min_a, 0.22)
        self.assertEqual(high.main_stable_hold_s, 0)
        self.assertEqual(high.main_stability_status, "away_from_minimum")
        self.assertEqual(a.observe(sample(120, 0.22)).metrics.main_stable_hold_s, 0)
        self.assertEqual(a.observe(sample(180, 0.22)).metrics.main_stable_hold_s, 60)

    def test_one_tick_transient_does_not_destroy_candidate(self):
        a = self.analyzer()
        a.observe(sample(0, 0.22))
        a.observe(sample(30, 0.22))
        self.assertEqual(a.observe(sample(60, 0.23)).metrics.main_stability_status, "rise_pending")
        self.assertEqual(a.observe(sample(90, 0.22)).metrics.main_stable_hold_s, 90)

    def test_new_minimum_restarts_hold(self):
        a = self.analyzer()
        a.observe(sample(0, 0.23))
        self.assertEqual(a.observe(sample(60, 0.23)).metrics.main_stable_hold_s, 60)
        m = a.observe(sample(90, 0.22)).metrics
        self.assertEqual(m.current_min_a, 0.22)
        self.assertEqual(m.main_stable_hold_s, 0)

    def test_gap_and_cc_do_not_credit_unobserved_time(self):
        a = self.analyzer()
        a.observe(sample(0, 0.22))
        a.observe(sample(30, 0.22))
        self.assertEqual(a.observe(sample(300, 0.22)).metrics.main_stable_hold_s, 0)
        self.assertEqual(a.observe(sample(330, 0.22, cv=False)).metrics.main_stable_hold_s, 0)
        self.assertEqual(a.observe(sample(360, 0.22)).metrics.main_stable_hold_s, 0)

    def test_mix_imin_age_and_delta_not_reinterpreted(self):
        a = SignalAnalyzer()
        a.reset_stage("mix", target_voltage_v=16.5)
        a.observe(sample(0, 0.22))
        a.observe(sample(60, 0.23))
        m = a.observe(sample(120, 0.23)).metrics
        self.assertEqual(m.seconds_since_current_min, 120)
        self.assertIsNone(m.main_stable_hold_s)
        self.assertEqual(m.main_stability_status, "not_applicable")


if __name__ == "__main__":
    unittest.main()
