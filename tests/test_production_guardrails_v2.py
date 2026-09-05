import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pb_domain import ChargeIntent
from production_controller import ProductionChargeControllerV2
from production_guardrails_v2 import (
    LEGACY_VIN_AUTHORITY_DISABLED,
    install_production_guardrails,
    validate_cooling_pause,
)


class DummyHass:
    pass


class ProductionGuardrailsTests(unittest.IsolatedAsyncioTestCase):
    def _controller(self):
        controller = ProductionChargeControllerV2(DummyHass(), authoritative=True)
        controller.battery_type = controller.PROFILE_EFB
        controller.ah_capacity = 60
        controller._v2_intent = ChargeIntent.RECOVERY
        controller.total_start_time = 100.0
        controller._stage_start_ah = 1.0
        controller._last_known_output_on = False
        controller._initialize_shadow_session(started_at=100.0)
        return controller

    def _install(self, controller):
        app = SimpleNamespace(
            charge_controller=controller,
            MIN_INPUT_VOLTAGE=60.0,
        )
        install_production_guardrails(app)
        return app

    def test_legacy_vin_threshold_is_neutralized_at_production_composition(self):
        controller = self._controller()
        app = self._install(controller)
        self.assertEqual(app.MIN_INPUT_VOLTAGE, LEGACY_VIN_AUTHORITY_DISABLED)
        self.assertTrue(app._v2_vin_psu_health_only)
        # Mirrors the two legacy gate shapes: both must become inert for any finite Vin.
        for vin in (0.0, 10.0, 40.0, 59.9, 64.0):
            self.assertFalse(vin > 0 and vin < app.MIN_INPUT_VOLTAGE)
            self.assertTrue(vin >= app.MIN_INPUT_VOLTAGE)

    async def test_safe_wait_cooling_never_reenables_output_and_freezes_relax_clock(self):
        controller = self._controller()
        controller.current_stage = controller.STAGE_SAFE_WAIT
        controller.stage_start_time = 100.0
        controller._safe_wait_start = 100.0
        controller._safe_wait_next_stage = controller.STAGE_DONE
        controller._safe_wait_target_v = 13.8
        controller._safe_wait_target_i = 1.0
        self._install(controller)

        with patch.object(controller, "_save_session", return_value=None):
            with patch("charge_logic.time.time", return_value=1000.0):
                actions = await controller.tick(
                    voltage=13.5,
                    current=0.0,
                    temp_ext=40.0,
                    is_cv=False,
                    ah=5.0,
                    output_is_on=False,
                    is_cc=False,
                )
            self.assertEqual(controller.current_stage, controller.STAGE_COOLING)
            self.assertTrue(actions.get("turn_off"))
            pause = controller._v2_cooling_pause
            self.assertIsInstance(pause, dict)
            self.assertAlmostEqual(float(pause["source_safe_wait_start"]), 100.0)
            self.assertEqual(pause["source_stage"], controller.STAGE_SAFE_WAIT)

            with patch("charge_logic.time.time", return_value=4600.0):
                actions = await controller.tick(
                    voltage=13.2,
                    current=0.0,
                    temp_ext=35.0,
                    is_cv=False,
                    ah=5.0,
                    output_is_on=False,
                    is_cc=False,
                )

        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertTrue(actions.get("turn_off"))
        self.assertNotIn("turn_on", actions)
        self.assertNotIn("set_voltage", actions)
        self.assertNotIn("set_current", actions)
        self.assertNotIn("set_ovp", actions)
        self.assertNotIn("set_ocp", actions)
        # 900 s elapsed before Cooling; the 3600 s Cooling interval is excluded.
        self.assertAlmostEqual(4600.0 - controller._safe_wait_start, 900.0, places=3)

    async def test_corrupt_in_memory_cooling_token_fails_closed_before_resume(self):
        controller = self._controller()
        controller.current_stage = controller.STAGE_COOLING
        controller.stage_start_time = 1000.0
        controller._v2_cooling_pause = None
        stopped = []

        def stop(clear_session=True):
            stopped.append(clear_session)
            controller.current_stage = controller.STAGE_IDLE

        controller.stop = stop
        self._install(controller)
        actions = await controller.tick(
            voltage=13.2,
            current=0.0,
            temp_ext=35.0,
            is_cv=False,
            ah=5.0,
            output_is_on=False,
            is_cc=False,
        )
        self.assertTrue(actions.get("emergency_stop"))
        self.assertTrue(actions.get("turn_off"))
        self.assertEqual(stopped, [True])
        self.assertEqual(controller.current_stage, controller.STAGE_IDLE)

    def test_restore_with_missing_v2_cooling_token_is_rejected(self):
        controller = self._controller()
        controller.current_stage = controller.STAGE_COOLING
        controller._v2_cooling_pause = None
        stopped = []

        def legacy_restore(_voltage, _current, _ah):
            return True, "legacy cooling restored"

        def stop(clear_session=True):
            stopped.append(clear_session)
            controller.current_stage = controller.STAGE_IDLE

        controller.try_restore_session = legacy_restore
        controller.stop = stop
        self._install(controller)

        ok, message = controller.try_restore_session(13.0, 0.0, 5.0)
        self.assertFalse(ok)
        self.assertIn("automatic resume is disabled", message)
        self.assertEqual(stopped, [True])
        self.assertEqual(controller.current_stage, controller.STAGE_IDLE)

    def test_safe_wait_pause_requires_its_own_frozen_clock(self):
        controller = self._controller()
        controller.current_stage = controller.STAGE_COOLING
        controller._safe_wait_target_v = 13.8
        controller._safe_wait_target_i = 1.0
        controller._safe_wait_next_stage = controller.STAGE_DONE
        pause = {
            "source_stage": controller.STAGE_SAFE_WAIT,
            "entered_at": 1000.0,
            "source_stage_start_time": 100.0,
            "target_v": 0.0,
            "target_i": 0.0,
        }
        valid, reason = validate_cooling_pause(controller, pause)
        self.assertFalse(valid)
        self.assertEqual(reason, "cooling_safe_wait_clock_missing")


if __name__ == "__main__":
    unittest.main()
