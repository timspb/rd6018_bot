"""D070: guarded MAIN legacy restore is held until a real execution owner exists.

Tests use a temporary file and an inert controller: never HA or RD hardware.
"""
import json
from pathlib import Path
import tempfile
import time
import unittest

from charge_controller import ManagedChargeController
from runtime.charge.persistence import restore_session
from runtime.charge.strategy.main_guard_session import GUARD_KEY


class GuardedLegacyRestoreHoldTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.session_file = Path(self.directory.name) / "charge_session.json"

    def document(self, *, chemistry="EFB", seconds_old=10, guarded=True, journal=None):
        data = {
            "saved_at": time.time() - seconds_old,
            "profile": chemistry,
            "stage": "Main Charge",
            "ah_limit": 60,
            "v2_trace_session_id": "sid-1",
            "v2_battery_id": "battery-1",
        }
        if guarded:
            data[GUARD_KEY] = {"journal_schema": 1} if journal is None else journal
        return data

    def write(self, document):
        self.session_file.write_text(json.dumps(document), encoding="utf-8")
        return self.session_file.read_bytes()

    def test_guarded_sessions_are_held_before_any_controller_mutation(self):
        for chemistry in ("EFB", "Ca/Ca"):
            with self.subTest(chemistry=chemistry):
                original = self.write(self.document(chemistry=chemistry))
                controller = ManagedChargeController(None)
                stage_before = controller.current_stage
                profile_before = controller.battery_type
                ok, reason = restore_session(
                    controller, voltage=12.4, current=0.0, ah=1.0,
                    session_file=str(self.session_file),
                )
                self.assertFalse(ok)
                self.assertIn("owner/readback reconciliation", reason)
                self.assertEqual(controller.current_stage, stage_before)
                self.assertEqual(controller.battery_type, profile_before)
                self.assertEqual(self.session_file.read_bytes(), original)

    def test_corrupt_or_pending_guard_cannot_be_ignored_as_optional(self):
        for journal in (None, {}, {"pending": {"proposal_id": "unresolved"}}):
            with self.subTest(journal=journal):
                original = self.write(self.document(journal=journal))
                controller = ManagedChargeController(None)
                ok, reason = restore_session(
                    controller, 12.4, 0.0, 1.0,
                    session_file=str(self.session_file),
                )
                self.assertFalse(ok)
                self.assertIsNotNone(reason)
                self.assertEqual(self.session_file.read_bytes(), original)

    def test_expired_guarded_checkpoint_is_not_deleted_by_legacy_restore(self):
        old = self.write(self.document(seconds_old=3 * 86400))
        controller = ManagedChargeController(None)
        ok, _ = restore_session(
            controller, 12.4, 0.0, 1.0,
            session_file=str(self.session_file),
        )
        self.assertFalse(ok)
        self.assertTrue(self.session_file.exists())
        self.assertEqual(self.session_file.read_bytes(), old)

    def test_non_mapping_session_cannot_restore_or_change_controller(self):
        self.write(["invalid", "session"])
        controller = ManagedChargeController(None)
        stage = controller.current_stage
        ok, _ = restore_session(
            controller, 12.4, 0.0, 1.0,
            session_file=str(self.session_file),
        )
        self.assertFalse(ok)
        self.assertEqual(controller.current_stage, stage)

    def test_unguarded_expired_session_retains_legacy_expiry_behavior(self):
        self.write(self.document(guarded=False, seconds_old=3 * 86400))
        controller = ManagedChargeController(None)
        ok, _ = restore_session(
            controller, 12.4, 0.0, 1.0,
            session_file=str(self.session_file),
        )
        self.assertFalse(ok)
        # Do not assert the global path used by the historical controller's
        # _clear_session_file here; this test protects ordinary non-guard paths
        # from acquiring an unintended Guard hold.

if __name__ == "__main__":
    unittest.main()
