import unittest
from unittest.mock import patch

from charge_logic import ChargeController


class DummyHass:
    pass


class ControllerThermalSafetyMatrixTests(unittest.IsolatedAsyncioTestCase):
    def _controller(self, now: float = 10000.0) -> ChargeController:
        controller = ChargeController(DummyHass())
        controller.current_stage = controller.STAGE_MAIN
        controller.battery_type = controller.PROFILE_EFB
        controller.ah_capacity = 70
        controller.stage_start_time = now - 1800
        controller.total_start_time = now - 1800
        controller._last_known_output_on = True
        controller._last_save_time = now
        controller._save_session = lambda *args, **kwargs: None
        return controller

    async def _tick(self, controller, *, now, temp, output_on=True):
        with patch("charge_logic.time.time", return_value=now):
            return await controller.tick(
                14.6,
                2.0 if output_on else 0.0,
                temp,
                False,
                10.0,
                output_on,
                is_cc=True,
            )

    async def test_missing_battery_temperature_is_emergency_fail_closed(self):
        controller = self._controller()
        actions = await self._tick(controller, now=10000.0, temp=None)

        self.assertTrue(actions.get("emergency_stop"))
        self.assertTrue(actions.get("full_reset"))
        self.assertEqual(actions.get("log_event"), "EMERGENCY_TEMP_INVALID")

    async def test_35c_warns_but_does_not_pause(self):
        controller = self._controller()
        actions = await self._tick(controller, now=10000.0, temp=35.0)

        self.assertFalse(actions.get("turn_off", False))
        self.assertFalse(actions.get("emergency_stop", False))
        self.assertEqual(controller.current_stage, controller.STAGE_MAIN)
        self.assertTrue(controller._temp_warning_alerted)

    async def test_40c_pauses_to_cooling_and_requests_output_off(self):
        controller = self._controller()
        actions = await self._tick(controller, now=10000.0, temp=40.0)

        self.assertEqual(controller.current_stage, controller.STAGE_COOLING)
        self.assertTrue(actions.get("turn_off"))
        self.assertFalse(actions.get("emergency_stop", False))
        self.assertEqual(controller._cooling_from_stage, controller.STAGE_MAIN)

    async def test_cooling_does_not_resume_above_35c(self):
        controller = self._controller()
        await self._tick(controller, now=10000.0, temp=40.0)

        actions = await self._tick(controller, now=10100.0, temp=35.1, output_on=False)

        self.assertEqual(controller.current_stage, controller.STAGE_COOLING)
        self.assertFalse(actions.get("turn_on", False))

    async def test_cooling_resumes_only_at_or_below_35c(self):
        controller = self._controller()
        await self._tick(controller, now=10000.0, temp=40.0)

        actions = await self._tick(controller, now=10100.0, temp=35.0, output_on=False)

        self.assertEqual(controller.current_stage, controller.STAGE_MAIN)
        self.assertTrue(actions.get("turn_on"))
        self.assertGreater(actions.get("set_voltage", 0.0), 0.0)
        self.assertGreater(actions.get("set_current", 0.0), 0.0)
        self.assertIsNotNone(actions.get("set_ovp"))
        self.assertIsNotNone(actions.get("set_ocp"))

    async def test_45c_is_emergency_stop_not_cooling_resume_path(self):
        controller = self._controller()
        actions = await self._tick(controller, now=10000.0, temp=45.0)

        self.assertTrue(actions.get("emergency_stop"))
        self.assertTrue(actions.get("full_reset"))
        self.assertIn("EMERGENCY_TEMP_CRITICAL", actions.get("log_event", ""))
        self.assertNotEqual(controller.current_stage, controller.STAGE_COOLING)


if __name__ == "__main__":
    unittest.main()
