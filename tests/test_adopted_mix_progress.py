"""Adopted MIX presenter uses caller-provided authoritative hold duration."""
import unittest
from types import SimpleNamespace
from runtime.ui.components.adopted_mix_progress import _observer_progress


class AdoptedMixProgressTests(unittest.TestCase):
    def test_configured_duration_not_hard_coded(self):
        observer = SimpleNamespace(finish_hold_started_at_s=100.0)
        text = _observer_progress(observer, "active", "CV", hold_seconds=3 * 3600, now_s=3700.0)
        self.assertIn("1\u0447 00\u043c / 3\u0447", text)
        observer.finish_hold_started_at_s = None
        text = _observer_progress(observer, "active", "CC", hold_seconds=3 * 3600, now_s=3700.0)
        self.assertIn("3\u0447", text)
        self.assertNotIn("2\u0447", text)

    def test_no_state_mutation(self):
        observer = SimpleNamespace(finish_hold_started_at_s=50.0)
        _observer_progress(observer, "active", "CV", hold_seconds=7200.0, now_s=150.0)
        self.assertEqual(observer.finish_hold_started_at_s, 50.0)
