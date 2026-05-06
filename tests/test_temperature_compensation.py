import unittest
from unittest.mock import patch

from ai_engine import format_ai_snapshot
from charge_logic import ChargeController, TEMP_COMP_MAX_DELTA_V


class _FakeHass:
    pass


class TemperatureCompensationTests(unittest.TestCase):
    def test_prep_target_uses_temp_ext(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_CA, 70)

        voltage, current = controller._prep_target(15.0)

        self.assertAlmostEqual(voltage, 12.18, places=2)
        self.assertAlmostEqual(current, 0.7)

    def test_agm_profile_uses_gentler_coefficient(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_AGM, 70)
        controller.current_stage = ChargeController.STAGE_MAIN

        voltage, current = controller._main_target(15.0)

        self.assertAlmostEqual(voltage, 14.56, places=2)
        self.assertAlmostEqual(current, 7.0)

    def test_temperature_compensation_clamps_positive_delta(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_CA, 70)
        controller.current_stage = ChargeController.STAGE_MAIN

        voltage, _ = controller._main_target(-10.0)

        self.assertAlmostEqual(voltage, 15.30, places=2)
        self.assertLessEqual(round(voltage - 14.7, 3), TEMP_COMP_MAX_DELTA_V)

    def test_snapshot_exposes_temperature_compensation(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_EFB, 70)
        controller.current_stage = ChargeController.STAGE_MAIN

        snapshot = controller.get_ai_stage_snapshot(15.0)
        temp_comp = snapshot["temperature_compensation"]
        text = format_ai_snapshot(snapshot)

        self.assertTrue(temp_comp["enabled"])
        self.assertAlmostEqual(temp_comp["base_v"], 14.8, places=2)
        self.assertAlmostEqual(temp_comp["final_v"], 14.98, places=2)
        self.assertIn("Temp comp: enabled=YES", text)
        self.assertIn("delta=+0.18V", text)

    def test_tick_updates_voltage_when_battery_warms_up(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_CA, 70)
        controller.current_stage = ChargeController.STAGE_MAIN
        controller._device_set_voltage = 14.70
        controller._device_set_current = 7.0
        controller._last_known_output_on = True

        with patch("charge_logic.time.time", return_value=1000.0):
            actions = __import__("asyncio").run(
                controller.tick(
                    voltage=14.80,
                    current=1.20,
                    temp_ext=35.0,
                    is_cv=True,
                    ah=8.0,
                    output_is_on=True,
                )
            )

        self.assertAlmostEqual(actions["set_voltage"], 14.52, places=2)
        self.assertAlmostEqual(actions["set_ovp"], 14.62, places=2)
        self.assertNotIn("set_current", actions)


if __name__ == "__main__":
    unittest.main()
