"""Compare production stage execution against native recipe dispatch on real controllers.

A separate controller is used per route. No RD6018 hardware or service calls.
"""
import unittest
from unittest.mock import patch

from charge_controller import ManagedChargeController
from application.charge_stage_tick import run_charge_stage_tick
from runtime.charge.programs.native_recipe_runtime import run_native_recipe_tick
from pb_domain import ChargeIntent


class _NoHardware:
    pass


def _controller(profile, intent, stage):
    host = ManagedChargeController(_NoHardware())
    host.battery_type = profile
    host.ah_capacity = 72
    host.current_stage = stage
    host._v2_intent = ChargeIntent(intent)
    host.stage_start_time = 1000.0
    host.total_start_time = 900.0
    host._stage_start_ah = 1.0
    host._v2_trace_session_id = "parity-session"
    host._v2_trace_started_at = 900.0
    host._last_known_output_on = True
    return host


class NativeRecipeLiveStageParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_and_mix_real_stage_ticks_same_actions_and_state(self):
        for profile in ("Ca/Ca", "EFB", "AGM"):
            for intent in ("normal", "recovery", "conditioning", "diagnostic"):
                for stage_key in ("STAGE_MAIN", "STAGE_MIX"):
                    template = ManagedChargeController(_NoHardware())
                    stage = getattr(template, stage_key)
                    native = _controller(profile, intent, stage)
                    baseline = _controller(profile, intent, stage)
                    kwargs = dict(
                        stage_before=stage, voltage=14.5 if stage_key == "STAGE_MAIN" else 16.0,
                        current=1.0, temp_ext=25.0, is_cv=True,
                        ah=2.0, output_is_on=True, manual_off_active=False,
                        is_cc=False, manual_active=False,
                    )
                    for timestamp in (1010.0, 1020.0, 1030.0):
                        with self.subTest(profile=profile,intent=intent,
                                          stage=stage_key,timestamp=timestamp):
                            with patch("time.time",return_value=timestamp):
                                with patch.object(baseline, "_save_session"):
                                    original = await run_charge_stage_tick(baseline, **kwargs)
                                with patch.object(native, "_save_session"):
                                    adapted = await run_native_recipe_tick(
                                        f"native_{profile.lower().replace('/', '_')}_{intent}",
                                        native, **kwargs)
                            self.assertEqual(adapted, original)
                            self.assertEqual(native.current_stage, baseline.current_stage)
                            self.assertEqual(native._v2_intent, baseline._v2_intent)
                            self.assertEqual(native.stage_start_time, baseline.stage_start_time)

