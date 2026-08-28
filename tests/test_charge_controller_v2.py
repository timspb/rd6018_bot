import unittest

from charge_controller_v2 import ChargeControllerV2
from pb_domain import BatteryCondition, ChargeIntent


class DummyHass:
    pass


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


if __name__ == "__main__":
    unittest.main()
