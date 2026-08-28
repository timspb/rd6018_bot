import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from charge_logic import ChargeController, EFB_MIX_MAX_HOURS, MAIN_STAGE_MAX_HOURS
from config import MAX_VOLTAGE


class DummyHass:
    pass


class ChargeLogicSafetyIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def _controller_at_stage(self, profile: str, stage: str) -> ChargeController:
        controller = ChargeController(DummyHass())
        controller.battery_type = profile
        controller.ah_capacity = 70
        controller.current_stage = stage
        controller.total_start_time = time.time() - 3600
        controller.stage_start_time = time.time() - 3600
        controller._stage_start_ah = 1.0
        controller._blanking_until = 0.0
        controller._delta_monitor_after = 0.0
        controller._last_log_time = time.time()
        controller._last_hourly_report = time.time()
        return controller

    def test_cold_efb_mix_target_is_clamped_after_temperature_compensation(self):
        controller = self._controller_at_stage(
            ChargeController.PROFILE_EFB,
            ChargeController.STAGE_MIX,
        )
        voltage, _ = controller._mix_target(10.0)
        self.assertEqual(voltage, MAX_VOLTAGE)

    async def test_manual_off_cannot_bypass_main_hard_timeout_or_escalate_to_mix(self):
        controller = self._controller_at_stage(
            ChargeController.PROFILE_CA,
            ChargeController.STAGE_MAIN,
        )
        controller.stage_start_time = time.time() - (MAIN_STAGE_MAX_HOURS * 3600 + 5)

        actions = await controller.tick(
            voltage=14.7,
            current=0.20,
            temp_ext=25.0,
            is_cv=True,
            is_cc=False,
            ah=12.0,
            output_is_on=True,
            manual_off_active=True,
        )

        self.assertTrue(actions.get("turn_off"))
        self.assertEqual(controller.current_stage, controller.STAGE_DONE)
        self.assertNotIn("set_voltage", actions)
        self.assertNotIn("set_current", actions)
        self.assertIn("без перехода на повышенное напряжение", actions.get("notify", ""))

    async def test_manual_off_cannot_bypass_efb_mix_hard_timeout(self):
        controller = self._controller_at_stage(
            ChargeController.PROFILE_EFB,
            ChargeController.STAGE_MIX,
        )
        controller.stage_start_time = time.time() - (EFB_MIX_MAX_HOURS * 3600 + 5)
        controller.total_start_time = controller.stage_start_time
        controller.finish_timer_start = None
        controller.v_max_recorded = 16.5
        controller.i_min_recorded = 0.5

        actions = await controller.tick(
            voltage=16.45,
            current=0.50,
            temp_ext=25.0,
            is_cv=True,
            is_cc=False,
            ah=14.0,
            output_is_on=True,
            manual_off_active=True,
        )

        self.assertTrue(actions.get("turn_off"))
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertEqual(controller._safe_wait_next_stage, controller.STAGE_DONE)

    def test_restore_clamps_legacy_target_voltage(self):
        now = time.time()
        payload = {
            "saved_at": now,
            "profile": ChargeController.PROFILE_EFB,
            "stage": ChargeController.STAGE_MAIN,
            "ah_limit": 70,
            "target_voltage": 17.2,
            "target_current": 1.0,
            "stage_start_time": now - 600,
            "total_start_time": now - 600,
            "start_ah": 10.0,
            "stage_start_ah": 10.0,
        }

        with tempfile.TemporaryDirectory() as tmp:
            session_path = os.path.join(tmp, "charge_session.json")
            with open(session_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)

            with patch("charge_logic.SESSION_FILE", session_path):
                controller = ChargeController(DummyHass())
                ok, _ = controller.try_restore_session(
                    voltage=14.0,
                    current=1.0,
                    ah=10.0,
                )

        self.assertTrue(ok)
        self.assertEqual(controller._restored_target_v, MAX_VOLTAGE)


if __name__ == "__main__":
    unittest.main()
