import json
import os
import tempfile
import unittest
from unittest.mock import patch

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

    @staticmethod
    def _legacy_session(*, intent=None):
        document = {
            "profile": "EFB",
            "stage": "Mix Mode",
            "stage_start_time": 900.0,
            "target_finish_time": None,
            "finish_timer_start": None,
            "ah_limit": 100,
            "start_ah": 0.0,
            "stage_start_ah": 0.0,
            "stage_start_voltage": 14.8,
            "stage_start_current": 3.0,
            "stage_start_temp": 25.0,
            "current_retries": 0,
            "target_voltage": 16.6,
            "target_current": 3.0,
            "agm_stage_idx": 0,
            "safe_wait_next_stage": None,
            "safe_wait_target_v": 0.0,
            "safe_wait_target_i": 0.0,
            "safe_wait_start": 0.0,
            "total_start_time": 800.0,
            "first_stage_hold_since": None,
            "first_stage_hold_current": None,
            "stuck_current_since": None,
            "stuck_current_value": None,
            "previous_stage": "Main Charge",
            "last_transition_reason": "legacy fixture",
            "stage_history": [],
            "saved_at": 1000.0,
        }
        if intent is not None:
            document.update(
                {
                    "v2_trace_session_id": "abc123",
                    "v2_trace_started_at": 800.0,
                    "v2_battery_id": "saved-efb",
                    "v2_intent": intent.value,
                    "v2_condition_before": BatteryCondition.UNKNOWN.value,
                    "v2_authoritative": True,
                }
            )
        return document

    def _restore_document(self, document):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            with open(session_file, "w", encoding="utf-8") as handle:
                json.dump(document, handle)

            controller = ProductionChargeControllerV2(DummyHass(), authoritative=True)
            with patch("charge_logic.SESSION_FILE", session_file), patch(
                "charge_controller_v2.SESSION_FILE", session_file
            ), patch("charge_logic.time.time", return_value=1100.0), patch(
                "charge_controller_v2.time.time", return_value=1100.0
            ):
                ok, _ = controller.try_restore_session(16.0, 2.0, 1.0)
                target = controller._get_target_v_i(25.0)
                context = controller.recovery_trace_context
                with open(session_file, "r", encoding="utf-8") as handle:
                    persisted = json.load(handle)
            return ok, target, context, persisted

    def test_pre_v2_restore_defaults_to_normal_and_clamps_recovery_voltage(self):
        ok, target, context, persisted = self._restore_document(self._legacy_session())

        self.assertTrue(ok)
        self.assertEqual(context["intent"], ChargeIntent.NORMAL)
        self.assertAlmostEqual(target[0], 14.8)
        self.assertEqual(persisted["v2_intent"], ChargeIntent.NORMAL.value)

    def test_v2_recovery_restore_preserves_recovery_intent_and_ceiling(self):
        ok, target, context, _ = self._restore_document(
            self._legacy_session(intent=ChargeIntent.RECOVERY)
        )

        self.assertTrue(ok)
        self.assertEqual(context["intent"], ChargeIntent.RECOVERY)
        self.assertAlmostEqual(target[0], 16.5)


if __name__ == "__main__":
    unittest.main()
