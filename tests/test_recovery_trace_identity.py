import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from charge_controller import ManagedChargeController


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
            patch("charge_controller.SESSION_FILE", self.session_file),
            patch("charge_controller.SESSION_FILE", self.session_file),
        )

    def test_new_modular_sessions_get_distinct_stable_ids(self):
        p1, p2 = self._session_patches()
        with p1, p2, patch("charge_controller.time.time", return_value=1000.0), patch(
            "charge_controller.time.time", return_value=1000.0
        ):
            profile = ManagedChargeController(DummyHass())
            profile.start(profile.PROFILE_EFB, 70)
            profile_id = profile.recovery_trace_context["session_id"]

        p1, p2 = self._session_patches()
        with p1, p2, patch("charge_controller.time.time", return_value=1100.0), patch(
            "charge_controller.time.time", return_value=1100.0
        ):
            second = ManagedChargeController(DummyHass())
            second.start(second.PROFILE_AGM, 70)
            second_id = second.recovery_trace_context["session_id"]

        self.assertTrue(profile_id)
        self.assertTrue(second_id)
        self.assertNotEqual(profile_id, second_id)

    def test_saved_trace_identity_survives_legacy_total_time_reestimation(self):
        p1, p2 = self._session_patches()
        with p1, p2, patch("charge_controller.time.time", return_value=1000.0), patch(
            "charge_controller.time.time", return_value=1000.0
        ):
            original = ManagedChargeController(DummyHass())
            original.start(original.PROFILE_EFB, 70)
            original.current_stage = original.STAGE_MAIN
            original._device_set_voltage = 14.8
            original._device_set_current = 7.0
            original_id = original.recovery_trace_context["session_id"]
            original_started_at = original.recovery_trace_context["started_at"]

        p1, p2 = self._session_patches()
        with p1, p2, patch("charge_controller.time.time", return_value=1100.0), patch(
            "charge_controller.time.time", return_value=1100.0
        ):
            original._save_session(voltage=14.2, current=1.0, ah=1.0)

        with open(self.session_file, "r", encoding="utf-8") as handle:
            saved = json.load(handle)
        self.assertEqual(saved["v2_trace_session_id"], original_id)
        self.assertAlmostEqual(saved["v2_trace_started_at"], original_started_at)

        restored = ManagedChargeController(DummyHass())
        p1, p2 = self._session_patches()
        with p1, p2, patch("charge_controller.time.time", return_value=1200.0), patch(
            "charge_controller.time.time", return_value=1200.0
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

        first = ManagedChargeController(DummyHass())
        p1, p2 = self._session_patches()
        with p1, p2, patch("charge_controller.time.time", return_value=1100.0), patch(
            "charge_controller.time.time", return_value=1100.0
        ):
            ok, _ = first.try_restore_session(14.0, 1.0, 1.0)
        self.assertTrue(ok)
        migrated_id = first.recovery_trace_context["session_id"]

        with open(self.session_file, "r", encoding="utf-8") as handle:
            enriched = json.load(handle)
        self.assertEqual(enriched["v2_trace_session_id"], migrated_id)

        second = ManagedChargeController(DummyHass())
        p1, p2 = self._session_patches()
        with p1, p2, patch("charge_controller.time.time", return_value=1150.0), patch(
            "charge_controller.time.time", return_value=1150.0
        ):
            ok, _ = second.try_restore_session(14.0, 1.0, 1.0)
        self.assertTrue(ok)
        self.assertEqual(second.recovery_trace_context["session_id"], migrated_id)

    def test_restore_enrichment_uses_one_canonical_write_and_preserves_old_keys(self):
        now = time.time()
        legacy = {
            "profile": "EFB", "stage": "Main Charge", "stage_start_time": now - 100.0,
            "ah_limit": 70, "target_voltage": 14.8, "target_current": 7.0,
            "total_start_time": now - 200.0, "saved_at": now,
            "stage_history": [], "migration_marker": {"kept": True},
        }
        with open(self.session_file, "w", encoding="utf-8") as handle:
            json.dump(legacy, handle)
        writer = __import__("runtime.charge.session_atomic", fromlist=["atomic_session_write"])
        with patch("charge_controller.SESSION_FILE", self.session_file), \
             patch("runtime.charge.persistence.SESSION_FILE", self.session_file), \
             patch("runtime.charge.persistence.atomic_session_write", wraps=writer.atomic_session_write) as atomic:
            restored = ManagedChargeController(DummyHass())
            ok, _ = restored.try_restore_session(14.0, 1.0, 1.0)
        self.assertTrue(ok)
        self.assertEqual(atomic.call_count, 1)
        with open(self.session_file, "r", encoding="utf-8") as handle:
            enriched = json.load(handle)
        self.assertEqual(enriched["migration_marker"], {"kept": True})
        self.assertEqual(enriched["v2_trace_session_id"], restored.recovery_trace_context["session_id"])
        self.assertFalse(list(__import__("pathlib").Path(self.tempdir.name).glob("*.v2.tmp")))

    def test_enrichment_io_failure_fails_restore_and_keeps_original_document(self):
        now = time.time()
        legacy = {
            "profile": "EFB", "stage": "Main Charge", "stage_start_time": now - 100.0,
            "ah_limit": 70, "target_voltage": 14.8, "target_current": 7.0,
            "total_start_time": now - 200.0, "saved_at": now,
            "stage_history": [],
        }
        original = json.dumps(legacy, indent=2)
        with open(self.session_file, "w", encoding="utf-8") as handle:
            handle.write(original)
        partial_temp = self.session_file + ".v2.tmp"
        with open(partial_temp, "w", encoding="utf-8") as handle:
            handle.write('{"partial":')
        with patch("charge_controller.SESSION_FILE", self.session_file), \
             patch("runtime.charge.persistence.SESSION_FILE", self.session_file), \
             patch("runtime.charge.session_atomic.os.replace", side_effect=OSError("disk full")):
            restored = ManagedChargeController(DummyHass())
            ok, _ = restored.try_restore_session(14.0, 1.0, 1.0)
        self.assertFalse(ok)
        self.assertEqual(restored.current_stage, restored.STAGE_IDLE)
        with open(self.session_file, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), original)
        with open(partial_temp, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), '{"partial":')
        self.assertFalse(list(__import__("pathlib").Path(self.tempdir.name).glob(".charge-session-*.tmp")))

    def test_guarded_checkpoint_is_rejected_without_identity_rewrite(self):
        from runtime.charge.strategy.main_current_guard import MainCurrentGuard
        from runtime.charge.strategy.main_guard_session import attach_guard, GUARD_KEY

        now = time.time()
        document = {
            "profile": "EFB", "stage": "Main Charge", "stage_start_time": now - 100.0,
            "ah_limit": 70, "target_voltage": 14.8, "target_current": 6.0,
            "total_start_time": now - 200.0, "saved_at": now,
            "stage_history": [], "v2_trace_session_id": "sid-guard",
            "v2_battery_id": "battery-guard",
        }
        guard = MainCurrentGuard.start(
            session_id="sid-guard", battery_id="battery-guard", segment_id="main-1",
            capacity_ah=70, recipe_initial_current_a=6.0,
        )
        document[GUARD_KEY] = attach_guard(
            document, guard, now_s=now, expected_revision=0
        )[GUARD_KEY]
        original = json.dumps(document, sort_keys=True)
        with open(self.session_file, "w", encoding="utf-8") as handle:
            handle.write(original)
        restored = ManagedChargeController(DummyHass())
        p1, p2 = self._session_patches()
        with p1, p2, patch("runtime.charge.persistence.SESSION_FILE", self.session_file):
            ok, _ = restored.try_restore_session(14.0, 1.0, 1.0)
        self.assertFalse(ok)
        with open(self.session_file, "r", encoding="utf-8") as handle:
            persisted = json.load(handle)
        self.assertEqual(persisted[GUARD_KEY]["revision"], document[GUARD_KEY]["revision"])
        self.assertEqual(persisted[GUARD_KEY]["sha256"], document[GUARD_KEY]["sha256"])
        self.assertEqual(json.dumps(persisted, sort_keys=True), original)


if __name__ == "__main__":
    unittest.main()
