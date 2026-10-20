"""Offline real controller -> single atomic canonical session writer tests."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import charge_controller
from charge_controller import ManagedChargeController
from production_controller import ProductionChargeController
from application.production_session_extensions import session_document_extensions
from runtime.charge.strategy.main_current_guard import MainCurrentGuard
from runtime.charge.strategy.main_guard_session import (
    GUARD_KEY, GuardJournalError, read_guard
)


class AtomicChargeSessionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "charge_session.json"
        self.now = time.time()

    def controller(self):
        controller = ManagedChargeController(None, battery_id="battery-actual")
        controller.battery_type = "EFB"
        controller.ah_capacity = 60
        controller.current_stage = controller.STAGE_MAIN
        controller.stage_start_time = self.now - 500
        controller.total_start_time = self.now - 1000
        controller._v2_trace_session_id = "verified-sid"
        controller._v2_trace_started_at = self.now - 1000
        controller._v2_battery_id = "battery-actual"
        return controller

    def save(self, controller):
        with patch.object(charge_controller, "SESSION_FILE", str(self.path)):
            controller._save_session(14.4, 0.8, 10.0)
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_real_serializer_single_document_contains_trace_identity(self):
        controller = self.controller()
        document = self.save(controller)
        self.assertEqual(document["v2_trace_session_id"], "verified-sid")
        self.assertEqual(document["v2_battery_id"], "battery-actual")
        self.assertEqual(document["stage"], controller.STAGE_MAIN)
        self.assertNotIn(GUARD_KEY, document)
        self.assertFalse(list(self.path.parent.glob(".charge-session-*.tmp")))

    def test_real_serializer_keeps_guard_across_periodic_saves(self):
        controller = self.controller()
        controller._main_current_guard = MainCurrentGuard.start(
            session_id="verified-sid", battery_id="battery-actual",
            segment_id="main-1", capacity_ah=60, recipe_initial_current_a=6.0
        )
        first = self.save(controller)
        self.assertEqual(first[GUARD_KEY]["revision"], 1)
        self.assertEqual(read_guard(first, session_id="verified-sid",
                                    battery_id="battery-actual",
                                    now_s=self.now)[0].hardware_limit_a, 6.0)
        restored_guard, _revision = read_guard(
            first, session_id="verified-sid", battery_id="battery-actual",
            now_s=self.now,
        )
        self.assertEqual(restored_guard.session_id, "verified-sid")
        self.assertEqual(restored_guard.battery_id, "battery-actual")
        self.assertEqual(restored_guard.capacity_ah, controller.ah_capacity)
        second = self.save(controller)
        self.assertEqual(second[GUARD_KEY]["revision"], 2)
        self.assertEqual(second["v2_trace_session_id"], "verified-sid")

    def test_guard_cannot_disappear_from_live_canonical_document(self):
        controller = self.controller()
        controller._main_current_guard = MainCurrentGuard.start(
            session_id="verified-sid", battery_id="battery-actual",
            segment_id="main-1", capacity_ah=60, recipe_initial_current_a=6.0
        )
        first = self.save(controller)
        controller._main_current_guard = None
        with self.assertRaisesRegex(GuardJournalError, "not_restored"):
            self.save(controller)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), first)

    def test_guard_canonical_writer_rejects_wider_current_target(self):
        controller = self.controller()
        controller._main_current_guard = MainCurrentGuard.start(
            session_id="verified-sid", battery_id="battery-actual",
            segment_id="main-1", capacity_ah=60, recipe_initial_current_a=6.0
        )
        original = self.save(controller)
        # Contradict the cap in an incoming device-programmed result.
        controller._device_set_current = 9.0
        controller._device_set_voltage = 14.4
        with self.assertRaisesRegex(GuardJournalError, "target_exceeds_ratchet"):
            self.save(controller)
        self.assertEqual(json.loads(self.path.read_text()), original)

    def test_guard_wrong_session_identity_fails_without_wiping_file(self):
        controller = self.controller()
        controller._main_current_guard = MainCurrentGuard.start(
            session_id="verified-sid", battery_id="battery-actual",
            segment_id="main-1", capacity_ah=60, recipe_initial_current_a=6.0
        )
        original = self.save(controller)
        controller._v2_trace_session_id = "different-session"
        with self.assertRaises(GuardJournalError):
            self.save(controller)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), original)

    def test_os_replace_failure_preserves_old_valid_session(self):
        controller = self.controller()
        original = self.save(controller)
        with patch("runtime.charge.session_atomic.os.replace", side_effect=OSError("synthetic crash")):
            self.save_without_readback(controller)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), original)
        self.assertFalse(list(self.path.parent.glob(".charge-session-*.tmp")))

    def test_production_continuation_metadata_is_in_one_atomic_write(self):
        controller = ProductionChargeController(None, battery_id="battery-actual")
        controller.battery_type = "EFB"
        controller.ah_capacity = 60
        controller.current_stage = controller.STAGE_MAIN
        controller.stage_start_time = self.now - 500
        controller.total_start_time = self.now - 1000
        controller._v2_trace_session_id = "verified-sid"
        controller._v2_trace_started_at = self.now - 1000
        controller._v2_battery_id = "battery-actual"
        controller._v2_cooling_pause = {"source_stage": controller.STAGE_MAIN}
        with patch.object(charge_controller, "SESSION_FILE", str(self.path)), \
             patch("runtime.charge.session_atomic.atomic_session_write", wraps=__import__(
                 "runtime.charge.session_atomic", fromlist=["atomic_session_write"]
             ).atomic_session_write) as writer:
            controller._save_session(14.4, 0.8, 10.0)
        self.assertEqual(writer.call_count, 1)
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(document["v2_cooling_pause"], controller._v2_cooling_pause)
        self.assertEqual(document["v2_trace_session_id"], "verified-sid")

    def test_real_production_mix_runtime_and_delta_metadata(self):
        controller = ProductionChargeController(None, battery_id="battery-actual")
        controller.battery_type = "EFB"
        controller.ah_capacity = 60
        controller.current_stage = controller.STAGE_MIX
        controller._v2_trace_session_id = "verified-sid"
        controller._delta_reported = True
        controller._delta_trigger_mode = "CV"
        controller.finish_timer_start = self.now - 30
        controller._v2_session_signal_context = {
            "stage": controller.STAGE_MIX, "session_id": "verified-sid",
            "mode": "CV", "output_on": True, "telemetry_valid": True,
            "cv_state": True, "current_min_a": 0.4,
        }
        controller._finish_evidence = {
            "version": 1, "mode": "CV", "session_id": "verified-sid",
            "reference_value": 0.4, "accepted_delta": 0.1,
            "accepted_at": self.now - 30,
        }
        mixed = session_document_extensions(controller, {})
        self.assertEqual(mixed["delta_reported"], True)
        self.assertEqual(mixed["delta_trigger_mode"], "CV")
        self.assertEqual(mixed["runtime_signal"]["mode"], "CV")
        self.assertEqual(mixed["finish_evidence"]["accepted_delta"], 0.1)
        controller.current_stage = controller.STAGE_MAIN
        cleared = session_document_extensions(controller, mixed)
        self.assertNotIn("delta_reported", cleared)
        self.assertNotIn("runtime_signal", cleared)
        self.assertNotIn("finish_evidence", cleared)

    def test_invalid_output_signal_does_not_persist_as_mix_proof(self):
        controller = ProductionChargeController(None, battery_id="battery-actual")
        controller.current_stage = controller.STAGE_MIX
        controller._v2_trace_session_id = "verified-sid"
        controller._v2_session_signal_context = {
            "stage": controller.STAGE_MIX, "session_id": "verified-sid",
            "mode": "CV", "output_on": None, "telemetry_valid": True,
            "cv_state": True, "current_min_a": 0.4,
        }
        self.assertNotIn(
            "runtime_signal",
            session_document_extensions(controller, {"runtime_signal": {"stale": True}}),
        )

    def save_without_readback(self, controller):
        with patch.object(charge_controller, "SESSION_FILE", str(self.path)):
            controller._save_session(14.4, 0.8, 10.0)


if __name__ == "__main__":
    unittest.main()
