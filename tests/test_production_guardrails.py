import unittest
from pathlib import Path
from unittest.mock import patch

from charge_controller import ManagedChargeController
from pb_domain import ChargeIntent
from production_controller import ProductionChargeController
from runtime.charge.runtime.cooling_guard import validate_cooling_pause


class DummyHass:
    pass


class ProductionGuardrailsTests(unittest.IsolatedAsyncioTestCase):
    def _controller(self):
        controller = ProductionChargeController(DummyHass())
        controller.battery_type = controller.PROFILE_EFB
        controller.ah_capacity = 60
        controller._v2_intent = ChargeIntent.RECOVERY
        controller.total_start_time = 100.0
        controller._stage_start_ah = 1.0
        controller._last_known_output_on = False
        controller._initialize_shadow_session(started_at=100.0)
        return controller

    def test_vin_policy_is_static_and_composition_has_no_guardrail_installer(self):
        root = Path(__file__).resolve().parents[1]
        runtime_source = (root / "runtime" / "production_runtime.py").read_text(
            encoding="utf-8"
        )
        bot_source = (root / "bot.py").read_text(encoding="utf-8")

        self.assertIn('MIN_INPUT_VOLTAGE = float("-inf")', runtime_source)
        self.assertIn("_v2_vin_psu_health_only = True", runtime_source)
        self.assertNotIn("install_production_guardrails", bot_source)
        self.assertNotIn("production_guardrails_v2", bot_source)

    async def test_safe_wait_cooling_never_reenables_output_and_freezes_relax_clock(self):
        controller = self._controller()
        controller.current_stage = controller.STAGE_SAFE_WAIT
        controller.stage_start_time = 100.0
        controller._safe_wait_start = 100.0
        controller._safe_wait_next_stage = controller.STAGE_DONE
        controller._safe_wait_target_v = 13.8
        controller._safe_wait_target_i = 1.0

        with patch.object(controller, "_save_session", return_value=None):
            with patch("time.time", return_value=1000.0):
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

            with patch("time.time", return_value=4600.0):
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
        for key in ("turn_on", "set_voltage", "set_current", "set_ovp", "set_ocp"):
            self.assertNotIn(key, actions)
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

        def stop(clear_session=True):
            stopped.append(clear_session)
            controller.current_stage = controller.STAGE_IDLE

        controller.stop = stop
        with patch.object(controller, "_read_legacy_session_document", return_value={}):
            with patch.object(
                ManagedChargeController,
                "try_restore_session",
                return_value=(True, "cooling restored"),
            ):
                ok, message = controller.try_restore_session(
                    13.0,
                    0.0,
                    5.0,
                    output_is_on=False,
                    is_cv=False,
                    is_cc=True,
                )

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
