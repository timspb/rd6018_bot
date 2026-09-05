import json
import os
import tempfile
import unittest
from unittest.mock import patch

from charge_controller_v2 import ChargeControllerV2


class DummyHass:
    pass


class RecoveryTraceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.session_file = os.path.join(self.tempdir.name, "charge_session.json")

    def tearDown(self):
        self.tempdir.cleanup()

    def _session_patches(self):
        return (
            patch("charge_logic.SESSION_FILE", self.session_file),
            patch("charge_controller_v2.SESSION_FILE", self.session_file),
        )

    def test_new_profile_and_custom_sessions_get_distinct_stable_ids(self):
        p1, p2 = self._session_patches()
        with p1, p2, patch("charge_logic.time.time", return_value=1000.0), patch(
            "charge_controller_v2.time.time", return_value=1000.0
        ):
            profile = ChargeControllerV2(DummyHass())
            profile.start(profile.PROFILE_EFB, 70)
            profile_id = profile.recovery_trace_context["session_id"]

        p1, p2 = self._session_patches()
        with p1, p2, patch("charge_logic.time.time", return_value=1100.0), patch(
            "charge_controller_v2.time.time", return_value=1100.0
        ):
            custom = ChargeControllerV2(DummyHass())
            custom.start_custom(
                main_voltage=14.8,
                main_current=5.0,
                delta_threshold=0.03,
                time_limit_hours=24,
                ah_capacity=70,
            )
            custom_id = custom.recovery_trace_context["session_id"]

        self.assertTrue(profile_id)
        self.assertTrue(custom_id)
        self.assertNotEqual(profile_id, custom_id)

    def test_saved_trace_identity_survives_legacy_total_time_reestimation(self):
        p1, p2 = self._session_patches()
        with p1, p2, patch("charge_logic.time.time", return_value=1000.0), patch(
            "charge_controller_v2.time.time", return_value=1000.0
        ):
            original = ChargeControllerV2(DummyHass())
            original.start(original.PROFILE_EFB, 70)
            original.current_stage = original.STAGE_MAIN
            original._device_set_voltage = 14.8
            original._device_set_current = 7.0
            original_id = original.recovery_trace_context["session_id"]
            original_started_at = original.recovery_trace_context["started_at"]

        p1, p2 = self._session_patches()
        with p1, p2, patch("charge_logic.time.time", return_value=1100.0), patch(
            "charge_controller_v2.time.time", return_value=1100.0
        ):
            original._save_session(voltage=14.2, current=1.0, ah=1.0)

        with open(self.session_file, "r", encoding="utf-8") as handle:
            saved = json.load(handle)
        self.assertEqual(saved["v2_trace_session_id"], original_id)
        self.assertAlmostEqual(saved["v2_trace_started_at"], original_started_at)

        restored = ChargeControllerV2(DummyHass())
        p1, p2 = self._session_patches()
        with p1, p2, patch("charge_logic.time.time", return_value=1200.0), patch(
            "charge_controller_v2.time.time", return_value=1200.0
        ):
            ok, _ = restored.try_restore_session(
                voltage=14.5,
                current=0.20,
                ah=5.0,
            )

        self.assertTrue(ok)
        self.assertEqual(restored.recovery_trace_context["session_id"], original_id)
        self.assertAlmostEqual(
            restored.recovery_trace_context["started_at"],
            original_started_at,
        )
        # The legacy timer is free to be reconstructed independently; trace identity
        # must not derive from that mutable estimate.
        self.assertNotEqual(restored.total_start_time, original_started_at)

    def test_pre_v2_session_gets_deterministic_migration_identity(self):
        legacy = {
            "profile": "EFB",
            "stage": "Main Charge",
            "stage_start_time": 900.0,
            "target_finish_time": None,
            "finish_timer_start": None,
            "ah_limit": 70,
            "start_ah": 0.0,
            "stage_start_ah": 0.0,
            "stage_start_voltage": 12.0,
            "stage_start_current": 7.0,
            "stage_start_temp": 25.0,
            "current_retries": 0,
            "target_voltage": 14.8,
            "target_current": 7.0,
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
            "previous_stage": None,
            "last_transition_reason": "",
            "stage_history": [],
            "saved_at": 1000.0,
        }
        with open(self.session_file, "w", encoding="utf-8") as handle:
            json.dump(legacy, handle)

        first = ChargeControllerV2(DummyHass())
        p1, p2 = self._session_patches()
        with p1, p2, patch("charge_logic.time.time", return_value=1100.0), patch(
            "charge_controller_v2.time.time", return_value=1100.0
        ):
            ok, _ = first.try_restore_session(14.0, 1.0, 1.0)
        self.assertTrue(ok)
        migrated_id = first.recovery_trace_context["session_id"]

        with open(self.session_file, "r", encoding="utf-8") as handle:
            enriched = json.load(handle)
        self.assertEqual(enriched["v2_trace_session_id"], migrated_id)

        second = ChargeControllerV2(DummyHass())
        p1, p2 = self._session_patches()
        with p1, p2, patch("charge_logic.time.time", return_value=1150.0), patch(
            "charge_controller_v2.time.time", return_value=1150.0
        ):
            ok, _ = second.try_restore_session(14.0, 1.0, 1.0)
        self.assertTrue(ok)
        self.assertEqual(second.recovery_trace_context["session_id"], migrated_id)


if __name__ == "__main__":
    unittest.main()
