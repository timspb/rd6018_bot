import unittest
from unittest.mock import patch

from charge_controller_v2 import ChargeControllerV2
from pb_domain import BatteryCondition, ChargeIntent


class DummyHass:
    pass


class ExplodingShadowRuntime:
    def observe(self, *args, **kwargs):
        raise RuntimeError("synthetic shadow failure")


class ChargeControllerV2Tests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_tick_keeps_legacy_actions_and_adds_shadow_only(self):
        controller = ChargeControllerV2(DummyHass())
        actions = await controller.tick(
            voltage=12.7,
            current=0.0,
            temp_ext=25.0,
            is_cv=False,
            ah=0.0,
            output_is_on=False,
            is_cc=False,
        )
        self.assertIn("recovery_shadow", actions)
        self.assertEqual(actions["recovery_shadow"]["status"], "ok")
        self.assertEqual(actions["recovery_shadow"]["decision"], "continue")
        self.assertNotIn("turn_on", actions)
        self.assertNotIn("turn_off", actions)

    async def test_invalid_temperature_is_fail_closed_in_both_layers(self):
        controller = ChargeControllerV2(DummyHass())
        controller.current_stage = controller.STAGE_MAIN
        controller._last_known_output_on = True
        actions = await controller.tick(
            voltage=14.4,
            current=0.8,
            temp_ext=None,
            is_cv=True,
            ah=5.0,
            output_is_on=True,
        )
        self.assertTrue(actions.get("emergency_stop"))
        self.assertEqual(actions["recovery_shadow"]["decision"], "hold_output_off")
        self.assertIsNone(actions["recovery_shadow"]["disagreement"])

    async def test_context_can_be_configured_while_idle(self):
        controller = ChargeControllerV2(DummyHass())
        controller.configure_recovery_context(
            battery_id="varta-agm-95",
            intent=ChargeIntent.RECOVERY,
            condition_before=BatteryCondition.REHYDRATED,
        )
        await controller.tick(
            voltage=12.7,
            current=0.0,
            temp_ext=25.0,
            is_cv=False,
            ah=0.0,
            output_is_on=False,
            is_cc=False,
        )
        self.assertEqual(controller.recovery_shadow_summary["evidence"].battery_id, "varta-agm-95")

    async def test_configure_context_is_blocked_during_active_charge(self):
        controller = ChargeControllerV2(DummyHass())
        controller.current_stage = controller.STAGE_MAIN
        with self.assertRaises(RuntimeError):
            controller.configure_recovery_context(battery_id="other")

    async def test_main_shadow_exposes_capacity_normalized_tail(self):
        controller = ChargeControllerV2(DummyHass())
        controller.current_stage = controller.STAGE_MAIN
        controller.battery_type = controller.PROFILE_EFB
        controller.ah_capacity = 200
        controller.stage_start_time = 900.0
        controller._v2_target_voltage_v = 14.8
        controller._last_known_output_on = True

        with patch("charge_logic.time.time", return_value=1000.0):
            actions = await controller.tick(
                voltage=14.75,
                current=0.70,
                temp_ext=25.0,
                is_cv=True,
                ah=20.0,
                output_is_on=True,
                is_cc=False,
            )

        first_stage = actions["recovery_shadow"]["first_stage"]
        self.assertEqual(first_stage["state"], "tail_ready")
        self.assertAlmostEqual(first_stage["tail_threshold_a"], 0.80)
        self.assertAlmostEqual(first_stage["current_c_rate"], 0.0035)
        trace = actions["recovery_shadow"]["trace_point"]
        self.assertEqual(trace["stage"], controller.STAGE_MAIN)
        self.assertAlmostEqual(trace["target_voltage_v"], 14.8)
        self.assertTrue(trace["is_cv"])
        self.assertFalse(trace["is_cc"])
        self.assertTrue(trace["output_on"])

    async def test_transition_audit_uses_plateau_state_before_legacy_resets_it(self):
        controller = ChargeControllerV2(DummyHass())
        controller.current_stage = controller.STAGE_MAIN
        controller.battery_type = controller.PROFILE_EFB
        controller.ah_capacity = 60
        controller.stage_start_time = 0.0
        controller.total_start_time = 0.0
        controller._v2_target_voltage_v = 14.8
        controller._last_known_output_on = True

        with patch("charge_logic.time.time", return_value=301.0):
            await controller.tick(
                voltage=14.8,
                current=0.60,
                temp_ext=23.0,
                is_cv=True,
                ah=0.5,
                output_is_on=True,
                is_cc=False,
            )
        self.assertEqual(controller.current_stage, controller.STAGE_MAIN)
        self.assertAlmostEqual(controller._stuck_current_since or 0.0, 301.0)

        with patch("charge_logic.time.time", return_value=2701.0):
            actions = await controller.tick(
                voltage=14.8,
                current=0.60,
                temp_ext=23.0,
                is_cv=True,
                ah=0.6,
                output_is_on=True,
                is_cc=False,
            )

        self.assertEqual(controller.current_stage, controller.STAGE_DESULFATION)
        audit = actions["recovery_shadow"]["transition_audit"]
        self.assertEqual(audit["first_stage_state"], "stuck_plateau")
        self.assertEqual(audit["code"], "legacy_hv_escalation_after_stuck_plateau")
        self.assertEqual(audit["severity"], "info")

    async def test_shadow_exception_does_not_invalidate_legacy_actions(self):
        controller = ChargeControllerV2(DummyHass())
        controller.current_stage = controller.STAGE_MAIN
        controller.battery_type = controller.PROFILE_EFB
        controller.ah_capacity = 70
        controller.stage_start_time = 900.0
        controller.total_start_time = 900.0
        controller._v2_target_voltage_v = 14.8
        controller._v2_runtime = ExplodingShadowRuntime()
        controller._last_known_output_on = True

        with patch("charge_logic.time.time", return_value=1000.0):
            actions = await controller.tick(
                voltage=14.2,
                current=2.0,
                temp_ext=25.0,
                is_cv=False,
                ah=4.0,
                output_is_on=True,
                is_cc=True,
            )

        shadow = actions["recovery_shadow"]
        self.assertEqual(shadow["status"], "error")
        self.assertEqual(shadow["error_type"], "RuntimeError")
        self.assertEqual(shadow["trace_point"]["stage"], controller.STAGE_MAIN)
        self.assertNotIn("emergency_stop", actions)
        self.assertEqual(controller.current_stage, controller.STAGE_MAIN)


if __name__ == "__main__":
    unittest.main()
