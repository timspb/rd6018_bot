"""Pinned SAFE_WAIT settings change only canonical relaxation decisions."""
import tempfile
import unittest

from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_session import (
    native_target_parameters, select_native_recipe_version,
)
from runtime.charge.strategy.final_safe_wait import (
    FinalSafeWaitAction, FinalSafeWaitContinuation, decide_final_safe_wait,
)
from runtime.charge.strategy.recovery_safe_wait import (
    RecoverySafeWaitAction, RecoverySafeWaitContinuation, decide_recovery_safe_wait,
)


class _Host:
    battery_type = "EFB"
    _v2_intent = "recovery"


class NativeSafeWaitOverridesTests(unittest.TestCase):
    def test_pinned_threshold_and_time_for_recovery_and_final_wait(self):
        with tempfile.TemporaryDirectory() as root:
            library = NativeRecipeDraftLibrary(root)
            library.save("recovery_copy", 1, {
                "schema": 1, "base_recipe_id": "native_efb_recovery",
                "execution_kind": "native_authority",
                "overrides": {
                    "charge.safe_wait.maximum_hours": 1.0,
                    "charge.safe_wait.target_margin_v": 1.0,
                },
            })
            host = _Host()
            host._native_recipe_session_selection = select_native_recipe_version(
                library, "recovery_copy", 1, profile="EFB", intent="recovery",
            )
            params = native_target_parameters(host, "SAFE_WAIT")
            self.assertEqual(params, {"max_hours": 1.0, "target_margin_v": 1.0})
            recovery = RecoverySafeWaitContinuation(
                source_stage="DESULFATION", next_stage="MAIN",
                target_voltage_v=14.7, target_current_a=1.0,
                started_at=100.0, session_id="test", recovery_attempt=0,
                agm_stage_idx=0, session_generation=50.0,
            )
            final = FinalSafeWaitContinuation(
                source_stage="MIX", next_stage="DONE",
                target_voltage_v=14.7, target_current_a=1.0,
                started_at=100.0, session_id="test",
                completion_reason="completed", session_generation=50.0,
            )
            for continuation, decide, expected in (
                (recovery, decide_recovery_safe_wait,
                 RecoverySafeWaitAction.REQUEST_MAIN_ENABLE),
                (final, decide_final_safe_wait,
                 FinalSafeWaitAction.REQUEST_STORAGE_ENABLE),
            ):
                with self.subTest(decide=decide.__name__):
                    # At 14.0 V the normal 0.5 V margin permits a transition,
                    # but the edited 1.0 V margin keeps waiting.
                    standard = decide(continuation, now_s=200.0,
                                      voltage_v=14.0, output_is_off=True)
                    custom = decide(continuation, now_s=200.0,
                                    voltage_v=14.0, output_is_off=True, **params)
                    self.assertEqual(standard.action, expected)
                    self.assertEqual(custom.reason, "relaxation_in_progress")
                    self.assertAlmostEqual(custom.threshold_v, 13.7)
                    # With voltage held above threshold, the new 1 h ceiling
                    # produces the existing verified-enable request.
                    at_limit = decide(continuation, now_s=3700.0,
                                      voltage_v=14.0, output_is_off=True, **params)
                    self.assertEqual(at_limit.action, expected)
                    self.assertEqual(at_limit.reason, "timeout")
                    denied = decide(continuation, now_s=3700.0,
                                    voltage_v=14.0, output_is_off=False, **params)
                    self.assertEqual(denied.reason, "fresh_output_off_required")
            library.save("recovery_copy", 2, {
                "schema": 1, "base_recipe_id": "native_efb_recovery",
                "execution_kind": "native_authority",
                "overrides": {"charge.safe_wait.maximum_hours": 2.0},
            })
            self.assertEqual(native_target_parameters(host, "SAFE_WAIT"), params)

    def test_unpinned_defaults_unchanged_and_invalid_settings_not_selectable(self):
        host = _Host()
        host._native_recipe_session_selection = None
        self.assertEqual(native_target_parameters(host, "SAFE_WAIT"), {})
        with tempfile.TemporaryDirectory() as root:
            library = NativeRecipeDraftLibrary(root)
            with self.assertRaises(ValueError):
                library.save("bad", 1, {
                    "schema": 1, "base_recipe_id": "native_efb_recovery",
                    "execution_kind": "native_authority",
                    "overrides": {"charge.safe_wait.maximum_hours": 25.0},
                })
