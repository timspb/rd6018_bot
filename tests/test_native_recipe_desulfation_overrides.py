"""Native DESULFATION draft settings use the existing bounded strategy owner."""
import tempfile
import unittest

from pb_domain import ChargeIntent
from production_controller import create_production_charge_host
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_session import select_native_recipe_version, native_target_parameters
from runtime.charge.strategy.desulfation import decide_desulfation, DesulfationAction


class _NoHardware:
    pass


class NativeDesulfationOverrideTests(unittest.TestCase):
    def test_pinned_recovery_voltage_current_and_time_reach_original_strategy(self):
        with tempfile.TemporaryDirectory() as root:
            store = NativeRecipeDraftLibrary(root)
            store.save("my_recovery", 1, {
                "schema": 1, "execution_kind": "native_authority",
                "base_recipe_id": "native_efb_recovery",
                "overrides": {
                    "charge.desulfation.base_voltage_v": 16.0,
                    "charge.desulfation.current_c_rate": 0.01,
                    "charge.desulfation.duration_hours": 1.0,
                },
            })
            selection = select_native_recipe_version(
                store,"my_recovery",1,profile="EFB",intent="recovery")
            host = create_production_charge_host(_NoHardware())
            host.start("EFB",72)
            host._v2_intent = ChargeIntent.RECOVERY
            default = host._desulf_target(25.)
            host._native_recipe_session_selection = selection
            adjusted = host._desulf_target(25.)
            self.assertAlmostEqual(adjusted[0]-default[0], -0.3)
            self.assertLess(adjusted[1], default[1])
            params = native_target_parameters(host,"DESULFATION")
            self.assertEqual(params["duration_hours"],1.0)
            self.assertEqual(
                decide_desulfation(active_elapsed_s=3599.,
                                   duration_hours=params["duration_hours"]).action,
                DesulfationAction.CONTINUE)
            self.assertEqual(
                decide_desulfation(active_elapsed_s=3600.,
                                   duration_hours=params["duration_hours"]).action,
                DesulfationAction.COMPLETE_TO_SAFE_WAIT)
            self.assertEqual(
                decide_desulfation(active_elapsed_s=3600.).action,
                DesulfationAction.CONTINUE)

    def test_diagnostic_copy_cannot_select_desulfation_settings(self):
        with tempfile.TemporaryDirectory() as root:
            store=NativeRecipeDraftLibrary(root)
            with self.assertRaises(ValueError):
                store.save("diag",1,{
                    "schema":1,"execution_kind":"native_authority",
                    "base_recipe_id":"native_efb_diagnostic",
                    "overrides":{"charge.desulfation.duration_hours":1.0},
                })
