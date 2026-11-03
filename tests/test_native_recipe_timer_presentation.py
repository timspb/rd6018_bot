"""Displayed recovery timer limits reflect pinned stage owner duration."""
import tempfile
import unittest

from pb_domain import ChargeIntent
from production_controller import create_production_charge_host
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_session import select_native_recipe_version
from runtime.charge.runtime.support import target_finish_time, stage_max_hours


class _NoHardware:
    pass


class NativeRecipeTimerPresentationTests(unittest.TestCase):
    def test_recovery_and_wait_timer_values_follow_pinned_session(self):
        with tempfile.TemporaryDirectory() as root:
            lib = NativeRecipeDraftLibrary(root)
            lib.save("copy", 1, {
                "schema": 1, "base_recipe_id": "native_efb_recovery",
                "execution_kind": "native_authority",
                "overrides": {
                    "charge.desulfation.duration_hours": 1.5,
                    "charge.safe_wait.maximum_hours": 3.0,
                },
            })
            host = create_production_charge_host(_NoHardware())
            host.start("EFB", 72)
            host._v2_intent = ChargeIntent.RECOVERY
            host._native_recipe_session_selection = select_native_recipe_version(
                lib,"copy",1,profile="EFB",intent="recovery")
            host.current_stage = host.STAGE_DESULFATION
            host.stage_start_time = 1000.0
            self.assertEqual(stage_max_hours(host), 1.5)
            self.assertEqual(target_finish_time(host), 6400.0)
            host.current_stage = host.STAGE_SAFE_WAIT
            host._safe_wait_start = 2000.0
            self.assertEqual(stage_max_hours(host), 3.0)
            self.assertEqual(target_finish_time(host), 12800.0)
            lib.save("copy", 2, {
                "schema": 1, "base_recipe_id": "native_efb_recovery",
                "execution_kind": "native_authority",
                "overrides": {"charge.safe_wait.maximum_hours": 5.0},
            })
            self.assertEqual(stage_max_hours(host), 3.0)

    def test_unpinned_stays_on_original_defaults(self):
        host = create_production_charge_host(_NoHardware())
        host.start("EFB", 72)
        host._v2_intent = ChargeIntent.NORMAL
        host._native_recipe_session_selection = None
        host.current_stage = host.STAGE_DESULFATION
        self.assertEqual(stage_max_hours(host), 2.0)
        host.current_stage = host.STAGE_SAFE_WAIT
        self.assertEqual(stage_max_hours(host), 2.0)
