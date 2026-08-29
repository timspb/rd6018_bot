import unittest

from pb_domain import BatteryCondition, ChargeIntent
from production_controller import ProductionChargeControllerV2


class DummyHass:
    pass


class ProductionControllerTests(unittest.TestCase):
    def _controller(self, profile: str, intent: ChargeIntent, capacity: int = 100):
        controller = ProductionChargeControllerV2(DummyHass(), authoritative=True)
        controller.configure_recovery_context(
            battery_id="fixture",
            intent=intent,
            condition_before=BatteryCondition.UNKNOWN,
        )
        controller.start(profile, capacity)
        return controller

    def test_normal_agm_cold_main_is_bounded_by_normal_recipe_ceiling(self):
        controller = self._controller(controller_profile := "AGM", ChargeIntent.NORMAL)
        self.assertEqual(controller_profile, controller.PROFILE_AGM)
        controller.current_stage = controller.STAGE_MAIN
        controller._agm_stage_idx = 3

        voltage_v, current_a = controller._main_target(0.0)

        self.assertAlmostEqual(voltage_v, 15.0)
        self.assertLessEqual(current_a, 10.0)

    def test_recovery_agm_cold_mix_never_exceeds_recovery_ceiling(self):
        controller = self._controller("AGM", ChargeIntent.RECOVERY)
        controller.current_stage = controller.STAGE_MIX

        voltage_v, current_a = controller._mix_target(0.0)

        self.assertAlmostEqual(voltage_v, 16.3)
        self.assertLessEqual(current_a, 3.0)

    def test_normal_intent_cannot_gain_recovery_voltage_from_mix_target(self):
        controller = self._controller("EFB", ChargeIntent.NORMAL)
        controller.current_stage = controller.STAGE_MIX

        voltage_v, _ = controller._mix_target(25.0)

        self.assertAlmostEqual(voltage_v, 14.8)

    def test_recovery_efb_temperature_compensation_is_bounded_at_16_5(self):
        controller = self._controller("EFB", ChargeIntent.RECOVERY)
        controller.current_stage = controller.STAGE_MIX

        voltage_v, current_a = controller._mix_target(0.0)

        self.assertAlmostEqual(voltage_v, 16.5)
        self.assertLessEqual(current_a, 5.0)


if __name__ == "__main__":
    unittest.main()
