"""Offline real controller -> single atomic canonical session writer tests."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import charge_controller
from charge_controller import ManagedChargeController
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

    def save_without_readback(self, controller):
        with patch.object(charge_controller, "SESSION_FILE", str(self.path)):
            controller._save_session(14.4, 0.8, 10.0)


if __name__ == "__main__":
    unittest.main()
