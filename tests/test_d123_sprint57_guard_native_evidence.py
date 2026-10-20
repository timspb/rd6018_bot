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
        "profile": "EFB", "stage": "Main Charge", "ah_limit": 60,
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

    def test_direct_native_reconciled_is_assessment_only_and_keeps_quarantine(self):
        document = guarded_document()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "charge_session.json"
            original = json.dumps(document, indent=2).encode()
            path.write_bytes(original)
            app = self.app_for(self.direct_client(native_live()), document)
            recovery = self.run_recovery(app, path)
            self.assertEqual(recovery.last_guard_assessment.status, "RECONCILED")
            self.assertIsNotNone(app.charge_controller._guarded_restore_candidate)
            self.assertFalse(app.charge_controller.is_active)
            self.assertEqual(path.read_bytes(), original)

    def test_ha_only_backend_has_no_native_guard_snapshot(self):
        client = HassClient(backend=types.SimpleNamespace(name="ha_esp"))
        self.assertIsNone(asyncio.run(client.get_native_guard_pre_on_snapshot()))

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

    def test_native_protection_iset_and_ocp_faults_are_assessed(self):
        document = guarded_document()
        cases = (
            (native_live(protection=2), "native_protection_not_normal"),
            (native_live(iset=5.0), "physical_iset_does_not_match_resume_target"),
            (native_live(ocp=6.3), "physical_ocp_not_confirmed"),
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
