import unittest
from unittest.mock import patch

from pb_domain import ChargeIntent
from production_controller import ProductionChargeControllerV2, V2_MIX_MAX_HOURS


class DummyHass:
    pass


class ProductionCoolingContractTests(unittest.IsolatedAsyncioTestCase):
    def _controller(self):
        controller = ProductionChargeControllerV2(DummyHass(), authoritative=True)
        controller.battery_type = controller.PROFILE_EFB
        controller.ah_capacity = 60
        controller._v2_intent = ChargeIntent.RECOVERY
        controller.current_stage = controller.STAGE_MAIN
        controller.stage_start_time = 100.0
        controller.total_start_time = 100.0
        controller._stage_start_ah = 1.0
        controller._v2_target_voltage_v = 14.8
        controller._last_known_output_on = True
        controller._v2_continuous_tail_since = 150.0
        controller._v2_continuous_tail_stage_start = 100.0
        controller._first_stage_hold_since = 150.0
        controller._first_stage_hold_current = 0.25
        controller._cv_since = 140.0
        controller._stuck_current_since = 800.0
        controller._stuck_current_value = 0.60
        controller._initialize_shadow_session(started_at=100.0)
        return controller

    async def test_main_cooling_freezes_active_clocks_and_resets_plateau_continuity(self):
        controller = self._controller()
        expected_target = controller._main_target(40.0)
        with patch.object(controller, "_save_session", return_value=None):
            with patch("charge_logic.time.time", return_value=1000.0):
                actions = await controller.tick(
                    voltage=14.8, current=0.25, temp_ext=40.0, is_cv=True,
                    ah=5.0, output_is_on=True, is_cc=False,
                )
            self.assertEqual(controller.current_stage, controller.STAGE_COOLING)
            self.assertTrue(actions.get("turn_off"))
            self.assertEqual(controller._cooling_from_stage, controller.STAGE_MAIN)
            self.assertAlmostEqual(controller._cooling_target_v, expected_target[0], places=2)
            self.assertAlmostEqual(controller._cooling_target_i, expected_target[1], places=2)
            self.assertIsNone(controller._stuck_current_since)

            with patch("charge_logic.time.time", return_value=4600.0):
                actions = await controller.tick(
                    voltage=13.6, current=0.0, temp_ext=35.0, is_cv=False,
                    ah=5.0, output_is_on=False, is_cc=False,
                )

        self.assertEqual(controller.current_stage, controller.STAGE_MAIN)
        self.assertTrue(actions.get("turn_on"))
        self.assertAlmostEqual(4600.0 - controller.stage_start_time, 900.0, places=3)
        self.assertAlmostEqual(4600.0 - controller._first_stage_hold_since, 850.0, places=3)
        self.assertAlmostEqual(4600.0 - controller._v2_continuous_tail_since, 850.0, places=3)
        self.assertIsNone(controller._stuck_current_since)
        self.assertEqual(controller._delta_trigger_count, 0)

    async def test_mix_finish_hold_is_sticky_but_clock_is_frozen_during_cooling(self):
        controller = self._controller()
        controller.current_stage = controller.STAGE_MIX
        controller.stage_start_time = 100.0
        controller._v2_target_voltage_v = 16.5
        controller.finish_timer_start = 500.0
        controller._delta_reported = True
        controller._delta_trigger_mode = "CV"

        with patch.object(controller, "_save_session", return_value=None):
            with patch("charge_logic.time.time", return_value=1000.0):
                await controller.tick(
                    voltage=16.45, current=0.30, temp_ext=40.0, is_cv=True,
                    ah=6.0, output_is_on=True, is_cc=False,
                )
            self.assertEqual(controller.current_stage, controller.STAGE_COOLING)

            with patch("charge_logic.time.time", return_value=4600.0):
                await controller.tick(
                    voltage=14.0, current=0.0, temp_ext=35.0, is_cv=False,
                    ah=6.0, output_is_on=False, is_cc=False,
                )

        self.assertEqual(controller.current_stage, controller.STAGE_MIX)
        self.assertAlmostEqual(controller.finish_timer_start, 4100.0, places=3)
        self.assertAlmostEqual(4600.0 - controller.finish_timer_start, 500.0, places=3)
        self.assertTrue(controller._delta_reported)
        self.assertEqual(controller._delta_trigger_mode, "CV")

    async def test_prep_returns_to_exact_profile_target_instead_of_legacy_14v_default(self):
        controller = self._controller()
        controller.current_stage = controller.STAGE_PREP
        controller.stage_start_time = 100.0
        controller._v2_target_voltage_v = 12.0
        expected_target = controller._prep_target(40.0)
        with patch.object(controller, "_save_session", return_value=None):
            with patch("charge_logic.time.time", return_value=1000.0):
                await controller.tick(
                    voltage=11.5, current=0.60, temp_ext=40.0, is_cv=False,
                    ah=1.5, output_is_on=True, is_cc=True,
                )
        self.assertEqual(controller.current_stage, controller.STAGE_COOLING)
        self.assertAlmostEqual(controller._cooling_target_v, expected_target[0], places=2)
        self.assertAlmostEqual(controller._cooling_target_i, expected_target[1], places=2)


class ProductionMixLimitTests(unittest.TestCase):
    def test_v2_mix_limits_are_the_agreed_fallback_windows(self):
        expected = {"Ca/Ca": 20.0, "EFB": 24.0, "AGM": 10.0}
        self.assertEqual(V2_MIX_MAX_HOURS, expected)
        controller = ProductionChargeControllerV2(DummyHass(), authoritative=True)
        for profile, hours in expected.items():
            controller.battery_type = profile
            self.assertEqual(controller._mix_limit_seconds(), hours * 3600.0)


if __name__ == "__main__":
    unittest.main()
