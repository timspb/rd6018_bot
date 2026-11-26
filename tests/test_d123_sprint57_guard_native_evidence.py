"""Sprint 57: synthetic Native Guard evidence remains diagnostic and quarantined."""
import asyncio
import json
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from application.execution_port import ExecutionPort
from application.guard_execution_owner_lock import GuardExecutionOwnerLock
from application.session_recovery_guard import SessionRecoveryGuard
from hass_api import HassClient
from runtime.charge.session import GuardedRestoreCandidate
from runtime.charge.strategy.main_current_guard import MainCurrentGuard
from runtime.charge.strategy.main_guard_session import attach_guard
from runtime.physical.connectors.esp_direct import ESPDirectConnector
from runtime.startup_recovery import StartupRecovery


def guarded_document():
    guard = MainCurrentGuard.start(
        session_id="sid", battery_id="battery", segment_id="main",
        capacity_ah=60, recipe_initial_current_a=6,
    )
    doc = {
        "saved_at": time.time(),
        "profile": "EFB", "stage": "Main Charge", "ah_limit": 60,
        "target_current": 6.0,
        "v2_trace_session_id": "sid", "v2_battery_id": "battery",
    }
    return attach_guard(doc, guard, now_s=time.time(), expected_revision=0)


def guard_from(document):
    from runtime.charge.strategy.main_guard_session import read_guard

    guard, _ = read_guard(document, session_id="sid", battery_id="battery",
                          now_s=time.time())
    return guard


def native_live(*, iset=6.0, ocp=6.1, protection=0, age=0.1):
    now = time.monotonic() - age
    keys = (
        "output_state_code_v2", "set_current_readback_v2",
        "ocp_readback_v2", "protection_code",
    )
    values = {
        "output_state_code_v2": 0, "set_current_readback_v2": iset,
        "ocp_readback_v2": ocp, "protection_code": protection,
    }
    values["_meta"] = {
        key: {
            "source": "esp_native_api", "status": "ok",
            "native_type": "SensorState", "age_s": age,
            "subscription_timestamp_monotonic": now,
        }
        for key in keys
    }
    return values


class Sprint57NativeEvidenceTests(unittest.TestCase):
    def direct_client(self, live, *, lease=True, lease_age=0.1):
        backend = ESPDirectConnector.__new__(ESPDirectConnector)

        async def get_all_live():
            return live

        async def get_state(_entity):
            return lease, {
                "source": "esp_native_api", "status": "ok",
                "native_type": "BinarySensorState",
                "subscription_timestamp_monotonic": time.monotonic() - lease_age,
            }

        backend.get_all_live = get_all_live
        backend.get_state = get_state
        return HassClient(backend=backend)

    def app_for(self, client, document):
        controller = types.SimpleNamespace(
            is_active=False,
            _guarded_restore_candidate=GuardedRestoreCandidate.capture(
                document, "direct_native_pre_on_reconciliation_required",
            ),
        )
        def restore(*_args, **kwargs):
            from runtime.charge.session import GuardedRestoreActivationPermit
            if not isinstance(kwargs.get("_guarded_activation_permit"), GuardedRestoreActivationPermit):
                return False, "permit required"
            controller.is_active = True
            controller._guarded_restore_candidate = None
            controller._guarded_restore_activated_off = True
            return True, "restored"
        controller.try_restore_session = restore
        app = types.SimpleNamespace(hass=client, charge_controller=controller)
        app.execution_port = ExecutionPort(object(), SessionRecoveryGuard())
        app.guard_execution_owner_lock = GuardExecutionOwnerLock()
        app.execution_port.bind_guard_owner_lock(app.guard_execution_owner_lock)
        return app

    def run_recovery(self, app, canonical_path):
        recovery = StartupRecovery(app, object(), object())
        with patch("runtime.startup_recovery.SESSION_FILE", str(canonical_path)):
            asyncio.run(recovery.replay_deferred_startup_restore())
        return recovery

    def test_direct_native_reconciled_activates_software_state_off_only(self):
        document = guarded_document()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "charge_session.json"
            original = json.dumps(document, indent=2).encode()
            path.write_bytes(original)
            app = self.app_for(self.direct_client(native_live()), document)
            recovery = self.run_recovery(app, path)
            self.assertEqual(recovery.last_guard_assessment.status, "RECONCILED")
            self.assertIsNone(app.charge_controller._guarded_restore_candidate)
            self.assertTrue(app.charge_controller.is_active)
            self.assertTrue(app.charge_controller._guarded_restore_activated_off)
            self.assertTrue(app.execution_port.guarded_restore_activated_off)
            self.assertFalse(asyncio.run(app.execution_port.request_verified_on()))
            self.assertEqual(path.read_bytes(), original)
            # A subsequent startup replay cannot enter the ordinary auto-resume
            # branch merely because controller.is_active became true.
            self.run_recovery(app, path)
            self.assertEqual(path.read_bytes(), original)

    def test_canonical_document_replaced_after_native_assessment_stays_quarantined(self):
        document = guarded_document()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "charge_session.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            client = self.direct_client(native_live())
            app = self.app_for(client, document)
            from runtime.startup_recovery import assess_main_guard_before_output_on as assessor

            def assess_then_replace(**kwargs):
                result = assessor(**kwargs)
                replacement = dict(document)
                replacement["replacement_marker"] = "changed-after-assessment"
                path.write_text(json.dumps(replacement), encoding="utf-8")
                return result

            with patch("runtime.startup_recovery.assess_main_guard_before_output_on",
                       side_effect=assess_then_replace):
                recovery = self.run_recovery(app, path)
            self.assertEqual(recovery.last_guard_assessment.status, "BLOCKED")
            self.assertEqual(recovery.last_guard_assessment.reason,
                             "candidate_or_canonical_changed_before_activation")
            self.assertIsNotNone(app.charge_controller._guarded_restore_candidate)
            self.assertFalse(app.charge_controller.is_active)

    def test_ha_only_backend_has_no_native_guard_snapshot(self):
        client = HassClient(backend=types.SimpleNamespace(name="ha_esp"))
        self.assertIsNone(asyncio.run(client.get_native_guard_pre_on_snapshot()))

    def test_native_snapshot_rejects_wrong_provenance_type_and_callback_time(self):
        for mutation in ("wrong_source", "wrong_type", "future_callback", "missing_callback"):
            with self.subTest(mutation=mutation):
                snapshot = native_live()
                meta = snapshot["_meta"]["set_current_readback_v2"]
                if mutation == "wrong_source":
                    meta["source"] = "ha_rest"
                elif mutation == "wrong_type":
                    meta["native_type"] = "NumberState"
                elif mutation == "future_callback":
                    meta["subscription_timestamp_monotonic"] = time.monotonic() + 1.0
                else:
                    meta.pop("subscription_timestamp_monotonic")
                client = self.direct_client(snapshot)
                self.assertIsNone(
                    asyncio.run(client.get_native_guard_pre_on_snapshot())
                )

    def test_invalid_lease_provenance_or_callback_time_blocks_restore_admission(self):
        document = guarded_document()
        for mutation in ("wrong_source", "wrong_type", "future_callback"):
            with self.subTest(mutation=mutation):
                path_root = tempfile.TemporaryDirectory()
                self.addCleanup(path_root.cleanup)
                path = Path(path_root.name) / "charge_session.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                client = self.direct_client(native_live())

                async def bad_lease_state(_entity):
                    meta = {
                        "source": "esp_native_api", "status": "ok",
                        "native_type": "BinarySensorState",
                        "subscription_timestamp_monotonic": time.monotonic(),
                    }
                    if mutation == "wrong_source":
                        meta["source"] = "ha_rest"
                    elif mutation == "wrong_type":
                        meta["native_type"] = "SensorState"
                    else:
                        meta["subscription_timestamp_monotonic"] += 1.0
                    return True, meta

                client._physical_backend.get_state = bad_lease_state
                app = self.app_for(client, document)
                recovery = self.run_recovery(app, path)
                self.assertEqual(recovery.last_guard_assessment.reason,
                                 "execution_owner_or_lease_unproven")
                self.assertIsNotNone(app.charge_controller._guarded_restore_candidate)
                self.assertFalse(app.charge_controller.is_active)

    def test_stale_callback_and_stale_lease_block_assessment(self):
        document = guarded_document()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "charge_session.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            stale = native_live(age=11.0)
            app = self.app_for(self.direct_client(stale), document)
            recovery = self.run_recovery(app, path)
            self.assertEqual(recovery.last_guard_assessment.reason,
                             "direct_native_callback_evidence_unavailable")
            self.assertEqual(app.charge_controller._guarded_restore_candidate.blocker,
                             "direct_native_callback_evidence_unavailable")
            fresh = native_live()
            app = self.app_for(self.direct_client(fresh, lease_age=11.0), document)
            recovery = self.run_recovery(app, path)
            self.assertEqual(recovery.last_guard_assessment.reason,
                             "execution_owner_or_lease_unproven")

    def test_native_reader_failure_during_registered_restore_keeps_candidate_held(self):
        """An unavailable direct callback cannot fall through to HA or restore."""
        document = guarded_document()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "charge_session.json"
            original = json.dumps(document, indent=2).encode()
            path.write_bytes(original)
            client = self.direct_client(native_live())
            client._physical_backend.get_all_live = unittest.mock.AsyncMock(
                side_effect=OSError("native callback unavailable")
            )
            app = self.app_for(client, document)
            recovery = self.run_recovery(app, path)
            self.assertEqual(recovery.last_guard_assessment.status, "BLOCKED")
            self.assertEqual(recovery.last_guard_assessment.reason,
                             "direct_native_callback_evidence_unavailable")
            self.assertIsNotNone(app.charge_controller._guarded_restore_candidate)
            self.assertFalse(app.charge_controller.is_active)
            self.assertTrue(app.execution_port.guarded_restore_activated_off is False)
            self.assertEqual(path.read_bytes(), original)

    def test_cancellation_during_native_pre_on_read_quarantines_and_never_restores(self):
        """Cancellation in the guarded branch is covered by the actual lock wrapper."""
        document = guarded_document()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "charge_session.json"
            original = json.dumps(document, indent=2).encode()
            path.write_bytes(original)
            client = self.direct_client(native_live())
            client.get_native_guard_pre_on_snapshot = unittest.mock.AsyncMock(
                side_effect=asyncio.CancelledError()
            )
            app = self.app_for(client, document)
            recovery = StartupRecovery(app, object(), object())
            with patch("runtime.startup_recovery.SESSION_FILE", str(path)):
                with self.assertRaises(asyncio.CancelledError):
                    asyncio.run(recovery.replay_deferred_startup_restore())
            self.assertTrue(app.execution_port.session_recovery_guard.quarantined)
            self.assertEqual(app.execution_port.session_recovery_guard.state.reason,
                             "deferred_restore_cancelled")
            self.assertIsNotNone(app.charge_controller._guarded_restore_candidate)
            self.assertFalse(app.charge_controller.is_active)
            self.assertFalse(app.execution_port.guarded_restore_activated_off)
            self.assertEqual(path.read_bytes(), original)

    def test_unexpected_native_restore_exception_quarantines_candidate(self):
        """A callback exception after candidate load must latch the existing guard."""
        document = guarded_document()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "charge_session.json"
            original = json.dumps(document, indent=2).encode()
            path.write_bytes(original)
            client = self.direct_client(native_live())
            client.get_native_guard_pre_on_snapshot = unittest.mock.AsyncMock(
                side_effect=RuntimeError("native restore callback failed")
            )
            app = self.app_for(client, document)
            recovery = StartupRecovery(app, object(), object())
            with patch("runtime.startup_recovery.SESSION_FILE", str(path)):
                with self.assertRaisesRegex(RuntimeError, "native restore callback failed"):
                    asyncio.run(recovery.replay_deferred_startup_restore())
            self.assertTrue(app.execution_port.session_recovery_guard.quarantined)
            self.assertEqual(
                app.execution_port.session_recovery_guard.state.reason,
                "deferred_restore_failed:RuntimeError",
            )
            self.assertIsNotNone(app.charge_controller._guarded_restore_candidate)
            self.assertFalse(app.charge_controller.is_active)
            self.assertFalse(app.execution_port.guarded_restore_activated_off)
            self.assertEqual(path.read_bytes(), original)

    def test_native_protection_and_iset_faults_block_guard_reconciliation(self):
        document = guarded_document()
        cases = (
            (native_live(protection=3), "safety_protection_not_clear"),
            (native_live(iset=5.0), "physical_iset_does_not_match_resume_target"),
        )
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "charge_session.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            for live, reason in cases:
                with self.subTest(reason=reason):
                    app = self.app_for(self.direct_client(live), document)
                    recovery = self.run_recovery(app, path)
                    self.assertEqual(recovery.last_guard_assessment.reason, reason)
                    self.assertIsNotNone(app.charge_controller._guarded_restore_candidate)

    def test_r16_ovp_ocp_do_not_block_guarded_off_restore(self):
        document = guarded_document()
        for code in (1, 2):
            with self.subTest(protection_code=code):
                with tempfile.TemporaryDirectory() as root:
                    path = Path(root) / "charge_session.json"
                    original = json.dumps(document).encode()
                    path.write_bytes(original)
                    app = self.app_for(self.direct_client(native_live(protection=code)), document)
                    recovery = self.run_recovery(app, path)
                    self.assertEqual(recovery.last_guard_assessment.status, "RECONCILED")
                    self.assertFalse(asyncio.run(app.execution_port.request_verified_on()))
                    self.assertEqual(path.read_bytes(), original)

    def test_ocp_is_not_an_extra_pre_on_main_guard_gate(self):
        # Canonical MAIN Guard reconciles fresh OFF/protection/Iset/journal
        # evidence. Hardware OCP is checked by separate physical safety
        # authorities; this pure reconciliation never authorizes Output ON.
        document = guarded_document()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "charge_session.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            app = self.app_for(self.direct_client(native_live(ocp=6.3)), document)
            recovery = self.run_recovery(app, path)
            self.assertEqual(recovery.last_guard_assessment.status, "RECONCILED")
            self.assertEqual(recovery.last_guard_assessment.reason,
                             "native_iset_matches_canonical_main_guard")
            self.assertTrue(app.charge_controller._guarded_restore_activated_off)
            self.assertFalse(asyncio.run(app.execution_port.request_verified_on()))

    def test_invalid_guard_and_changed_canonical_revision_remain_blocked(self):
        document = guarded_document()
        invalid = json.loads(json.dumps(document))
        invalid["main_current_guard_v1"]["snapshot"]["hardware_limit_a"] = 9
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "charge_session.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            app = self.app_for(self.direct_client(native_live()), invalid)
            recovery = self.run_recovery(app, path)
            self.assertIn("canonical_guard_untrustworthy",
                          recovery.last_guard_assessment.reason)
            self.assertIsNotNone(app.charge_controller._guarded_restore_candidate)

        newer = attach_guard(document, guard_from(document), now_s=time.time(),
                             expected_revision=1)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "charge_session.json"
            path.write_text(json.dumps(newer), encoding="utf-8")
            app = self.app_for(self.direct_client(native_live()), document)
            recovery = self.run_recovery(app, path)
            self.assertEqual(recovery.last_guard_assessment.reason,
                             "canonical_document_identity_or_revision_changed")
            self.assertIsNotNone(app.charge_controller._guarded_restore_candidate)

    def test_missing_owner_authorization_and_lease_are_rejected_by_existing_evaluator(self):
        from runtime.charge.strategy.main_guard_pre_on import assess_main_guard_before_output_on
        from runtime.charge.strategy.main_guard_session import read_guard

        document = guarded_document()
        guard, _ = read_guard(document, session_id="sid", battery_id="battery",
                              now_s=time.time())
        result = assess_main_guard_before_output_on(
            session_document=document, restored_guard=guard,
            native_live=native_live(), session_id="sid", battery_id="battery",
            profile="EFB", stage="Main Charge", target_current_a=6,
            owner_authorized=False, edge_lease_armed=False, now_epoch_s=time.time(),
        )
        self.assertEqual(result.reason, "execution_owner_or_lease_unproven")

    def test_guard_capture_isolated_from_later_nested_source_mutation(self):
        document = guarded_document()
        candidate = GuardedRestoreCandidate.capture(document, "held")
        original = candidate.document["main_current_guard_v1"]["snapshot"]["hardware_limit_a"]
        document["main_current_guard_v1"]["snapshot"]["hardware_limit_a"] = 99
        self.assertEqual(
            candidate.document["main_current_guard_v1"]["snapshot"]["hardware_limit_a"],
            original,
        )


if __name__ == "__main__":
    unittest.main()
