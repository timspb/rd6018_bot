"""Manual HMI presentation derives configured hold, no control authority."""
import unittest
from types import SimpleNamespace
from runtime.ui.components.manual_extrema_progress import _manual_extrema_status

class ManualExtremaPresenterTests(unittest.TestCase):
    def test_mix_hold_uses_caller_duration(self):
        request=SimpleNamespace(operation_mode="mix", stop=SimpleNamespace(delta=0.06))
        manual=SimpleNamespace(request=request, finish_hold_started_at=100.0, _imin=0.42, _vmax=16.8)
        text=_manual_extrema_status(manual, "CV", now_s=3700.0, mix_hold_seconds=3*3600)
        self.assertIn("1\u0447 00\u043c / 3\u0447", text)
        self.assertNotIn("/ 2\u0447", text)
        text=_manual_extrema_status(manual, "CC", now_s=20000.0, mix_hold_seconds=3*3600)
        self.assertIn("3\u0447 00\u043c / 3\u0447", text)
        self.assertEqual(manual.finish_hold_started_at, 100.0)

    def test_main_uses_existing_recipe_hold_hours(self):
        profile=SimpleNamespace(main=SimpleNamespace(confirmation_count=1, hold_hours=2.5))
        request=SimpleNamespace(operation_mode="main", profile=profile)
        manual=SimpleNamespace(request=request, main_min_confirmations=1, _imin=0.2, main_min_hold_started_at=100.)
        text=_manual_extrema_status(manual, "CV", now_s=3700., mix_hold_seconds=10800.)
        self.assertIn("2.5\u0447", text)
