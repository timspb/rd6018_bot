import unittest

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


if __name__ == "__main__":
    unittest.main()
