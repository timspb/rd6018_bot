"""D070: guarded MAIN legacy restore is held until a real execution owner exists.

Tests use a temporary file and an inert controller: never HA or RD hardware.
"""
import json
from pathlib import Path
import tempfile
import time
import unittest
import asyncio
from unittest.mock import patch

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
                self.assertEqual(
                    controller._guarded_restore_candidate.blocker,
                    "direct_native_pre_on_reconciliation_required",
                )
                self.assertEqual(controller._guarded_restore_candidate.session_id, "sid-1")

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
        with patch.object(controller, "_clear_session_file") as clear:
            ok, _ = restore_session(
                controller, 12.4, 0.0, 1.0,
                session_file=str(self.session_file),
            )
        self.assertFalse(ok)
        clear.assert_called_once()
        # Existing unguarded expiry semantics must not be altered.

    def test_locked_activation_permit_uses_canonical_restore_and_reconstructs_guard(self):
        from application.guard_execution_owner_lock import GuardExecutionOwnerLock
        from runtime.charge.session import (
            GuardedRestoreCandidate, _issue_guarded_restore_activation_permit,
            _valid_guarded_restore_activation_permit,
        )
        from runtime.charge.strategy.main_current_guard import MainCurrentGuard
        from runtime.charge.strategy.main_guard_session import attach_guard, read_guard

        guard = MainCurrentGuard.start(
            session_id="sid-1", battery_id="battery-1", segment_id="main",
            capacity_ah=60, recipe_initial_current_a=6,
        )
        document = {
            "saved_at": time.time(), "profile": "EFB", "stage": "Main Charge",
            "ah_limit": 60, "target_current": 6.0, "target_voltage": 14.4,
            "v2_trace_session_id": "sid-1", "v2_battery_id": "battery-1",
        }
        document = attach_guard(document, guard, now_s=time.time(), expected_revision=0)
        self.write(document)
        controller = ManagedChargeController(None)
        candidate = GuardedRestoreCandidate.capture(
            document, "held", canonical_bytes=self.session_file.read_bytes(),
        )
        controller._guarded_restore_candidate = candidate
        native = {"_meta": {
            key: {"subscription_timestamp_monotonic": time.monotonic()}
            for key in ("output_state_code_v2", "set_current_readback_v2",
                        "ocp_readback_v2", "protection_code")
        }}
        lock = GuardExecutionOwnerLock()

        async def restore():
            async with lock:
                permit = _issue_guarded_restore_activation_permit(
                    candidate=candidate, document=document, revision=1,
                    native_live=native, owner_task=asyncio.current_task(), owner_lock=lock,
                )
                with patch("runtime.charge.persistence.SESSION_FILE", str(self.session_file)), \
                     patch("charge_controller.SESSION_FILE", str(self.session_file)):
                    ok, _ = controller.try_restore_session(
                        0.0, 0.0, 0.0, output_is_on=False,
                        _guarded_activation_permit=permit,
                    )
                replay_valid = _valid_guarded_restore_activation_permit(
                    permit, document=document, session_id="sid-1",
                    battery_id="battery-1", revision=1,
                    candidate=controller._guarded_restore_candidate,
                )
                return ok, replay_valid

        restored, replay_valid = asyncio.run(restore())
        self.assertTrue(restored)
        self.assertFalse(replay_valid)
        self.assertEqual(controller.current_stage, controller.STAGE_MAIN)
        restored, revision = read_guard(
            document, session_id="sid-1", battery_id="battery-1", now_s=time.time(),
        )
        self.assertEqual(revision, 1)
        self.assertEqual(controller._main_current_guard, restored)
        self.assertEqual(controller._main_current_guard_revision, 1)
        self.assertTrue(controller._guarded_restore_activated_off)
        self.assertIsNone(controller._guarded_restore_candidate)

    def test_activation_permit_rejects_canonical_byte_tamper_at_restore_consume(self):
        from application.guard_execution_owner_lock import GuardExecutionOwnerLock
        from runtime.charge.session import (
            GuardedRestoreCandidate, _issue_guarded_restore_activation_permit,
        )
        from runtime.charge.strategy.main_current_guard import MainCurrentGuard
        from runtime.charge.strategy.main_guard_session import attach_guard

        guard = MainCurrentGuard.start(
            session_id="sid-1", battery_id="battery-1", segment_id="main",
            capacity_ah=60, recipe_initial_current_a=6,
        )
        document = {
            "saved_at": time.time(), "profile": "EFB", "stage": "Main Charge",
            "ah_limit": 60, "target_current": 6.0, "target_voltage": 14.4,
            "v2_trace_session_id": "sid-1", "v2_battery_id": "battery-1",
        }
        document = attach_guard(document, guard, now_s=time.time(), expected_revision=0)
        original = self.write(document)
        controller = ManagedChargeController(None)
        candidate = GuardedRestoreCandidate.capture(
            document, "held", canonical_bytes=original,
        )
        controller._guarded_restore_candidate = candidate
        native = {"_meta": {
            key: {"subscription_timestamp_monotonic": time.monotonic()}
            for key in ("output_state_code_v2", "set_current_readback_v2",
                        "ocp_readback_v2", "protection_code")
        }}
        lock = GuardExecutionOwnerLock()

        async def consume_after_replacement():
            async with lock:
                permit = _issue_guarded_restore_activation_permit(
                    candidate=candidate, document=document, revision=1,
                    native_live=native, owner_task=asyncio.current_task(),
                    owner_lock=lock,
                )
                self.session_file.write_bytes(original + b"\n")
                with patch("runtime.charge.persistence.SESSION_FILE", str(self.session_file)), \
                     patch("charge_controller.SESSION_FILE", str(self.session_file)):
                    return controller.try_restore_session(
                        0.0, 0.0, 0.0, output_is_on=False,
                        _guarded_activation_permit=permit,
                    )

        ok, _reason = asyncio.run(consume_after_replacement())
        self.assertFalse(ok)
        self.assertEqual(controller.current_stage, controller.STAGE_IDLE)
        self.assertIsNotNone(controller._guarded_restore_candidate)

if __name__ == "__main__":
    unittest.main()
