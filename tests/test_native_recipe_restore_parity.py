"""Native recipe identity across production session save/restore; no device I/O."""
import os
import tempfile
import unittest
from unittest.mock import patch

from pb_domain import ChargeIntent
from production_controller import create_production_charge_host
from runtime.charge.programs.native_recipe_runtime import run_native_recipe_tick


class _NoHardware:
    pass


class NativeRecipeRestoreParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_safe_wait_continuations_survive_normal_restore_without_enable(self):
        from runtime.charge.strategy.recovery_safe_wait import RecoverySafeWaitContinuation
        from runtime.charge.strategy.final_safe_wait import FinalSafeWaitContinuation

        for kind in ("recovery", "final"):
            for profile in ("Ca/Ca", "EFB", "AGM"):
                with self.subTest(kind=kind, profile=profile):
                    with tempfile.TemporaryDirectory() as directory:
                        path = os.path.join(directory, "charge_session.json")
                        now = 20000.0
                        original = create_production_charge_host(_NoHardware())
                        original.start(profile, 72)
                        original._v2_intent = ChargeIntent.RECOVERY
                        original.current_stage = original.STAGE_SAFE_WAIT
                        original.stage_start_time = now - 200
                        original._v2_trace_session_id = "native-session"
                        original._v2_trace_started_at = now - 4000
                        original._safe_wait_next_stage = (
                            original.STAGE_MAIN if kind == "recovery"
                            else original.STAGE_DONE
                        )
                        if kind == "recovery":
                            original._recovery_safe_wait = RecoverySafeWaitContinuation(
                                source_stage=original.STAGE_DESULFATION,
                                next_stage=original.STAGE_MAIN, target_voltage_v=14.7,
                                target_current_a=1.0, started_at=now-200,
                                session_id="native-session", recovery_attempt=0,
                                agm_stage_idx=0, session_generation=now-4000)
                        else:
                            original._final_safe_wait = FinalSafeWaitContinuation(
                                source_stage=original.STAGE_MIX,
                                next_stage=original.STAGE_DONE, target_voltage_v=13.8,
                                target_current_a=1.0, started_at=now-200,
                                session_id="native-session",
                                completion_reason="complete", session_generation=now-4000)
                        with patch("charge_controller.SESSION_FILE", path), patch(
                            "charge_controller.time.time", return_value=now
                        ):
                            original._save_session(14.8, 0.0, 8.0)
                            restored = create_production_charge_host(_NoHardware())
                            ok, reason = restored.try_restore_session(
                                14.8, 0.0, 8.0, output_is_on=False,
                                is_cv=False, is_cc=False,
                            )
                        self.assertTrue(ok, reason)
                        self.assertEqual(restored.current_stage, restored.STAGE_SAFE_WAIT)
                        self.assertEqual(restored.battery_type, profile)
                        self.assertEqual(restored._v2_intent, original._v2_intent)
                        self.assertEqual(restored._safe_wait_next_stage,
                                         original._safe_wait_next_stage)
                        candidate = (restored._recovery_safe_wait if kind == "recovery"
                                     else restored._final_safe_wait)
                        self.assertIsNotNone(candidate)
                        self.assertEqual(candidate.session_id, "native-session")
                        self.assertEqual(candidate.session_generation, now - 4000)

    async def test_recovered_native_session_uses_unchanged_profile_intent_and_owner(self):
        for profile in ("Ca/Ca", "EFB", "AGM"):
            for intent in ("normal", "recovery", "conditioning", "diagnostic"):
                with self.subTest(profile=profile, intent=intent):
                    with tempfile.TemporaryDirectory() as directory:
                        path = os.path.join(directory, "charge_session.json")
                        now = 20000.0
                        original = create_production_charge_host(_NoHardware())
                        original.start(profile, 72)
                        original._v2_intent = ChargeIntent(intent)
                        original.current_stage = original.STAGE_DESULFATION
                        original.stage_start_time = now - 1000
                        original.antisulfate_count = 1
                        original._v2_trace_session_id = "native-session"
                        original._v2_trace_started_at = now - 4000
                        with patch("charge_controller.SESSION_FILE", path), patch(
                            "charge_controller.time.time", return_value=now
                        ):
                            original._save_session(16.2, 0.5, 8.0)
                            restored = create_production_charge_host(_NoHardware())
                            ok, reason = restored.try_restore_session(
                                16.2, 0.5, 8.0, output_is_on=True,
                                is_cv=True, is_cc=False,
                            )
                        self.assertTrue(ok, reason)
                        self.assertEqual(restored.battery_type, profile)
                        self.assertEqual(restored._v2_intent, original._v2_intent)
                        self.assertEqual(restored.antisulfate_count, 1)
                        self.assertEqual(restored.current_stage, restored.STAGE_DESULFATION)
                        self.assertEqual(restored.stage_start_time,
                                         original.stage_start_time)
                        # Dispatcher is unchanged: validate it can be called on
                        # the restored host without needing a second recipe store.
                        kwargs = dict(
                            stage_before=restored.STAGE_DESULFATION,
                            voltage=16.2, current=0.5, temp_ext=25.0,
                            is_cv=True, ah=8.0, output_is_on=True,
                            manual_off_active=False, is_cc=False, manual_active=False,
                        )
                        with patch.object(restored, "_save_session"):
                            out = await run_native_recipe_tick(
                                f"native_{profile.lower().replace('/', '_')}_{intent}",
                                restored, **kwargs)
                        self.assertIsInstance(out, dict)