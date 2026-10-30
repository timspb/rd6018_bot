import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from runtime.ui.telegram.recovery_clearance import TelegramRecoveryAuthority, _approved_private_event
from runtime.charge.persistence import retire_controller_session, restore_session
from application.execution_port import ExecutionPort
from datetime import datetime, timezone
from application.controller_session_retirement import _ControllerSessionRetirement
from application.operator_recovery_clearance import OperatorRecoveryClearanceService, VerifiedOffEvidence
from application.session_recovery_guard import SessionRecoveryGuard, RecoveryGuardState
from application.guard_execution_owner_lock import GuardExecutionOwnerLock
from runtime.journal.recovery_quarantine import RecoveryQuarantineJournal


class RecoveryClearanceAdmissionTests(unittest.TestCase):
    def test_cold_reboot_clearance_uses_persisted_identity_and_never_resumes(self):
        class Controller:
            STAGE_IDLE, STAGE_MAIN, STAGE_MIX = "IDLE", "MAIN", "MIX"
            def __init__(self): self.current_stage = self.STAGE_IDLE
            def _clear_restored_targets(self): raise AssertionError("idle retirement must not mutate restored targets")
        class Owner:
            def __init__(self): self.off_calls = 0
            async def turn_off(self): self.off_calls += 1; return True
            async def get_all_live(self):
                raise AssertionError("cached live state must not prove native OFF")
            async def get_native_physical_output_report(self):
                return 0, {"native_type": "SensorState", "status": "ok", "age_s": 0.1,
                           "subscription_timestamp_monotonic": time.monotonic()}
        with tempfile.TemporaryDirectory() as temp:
            session_file, journal_file = Path(temp) / "charge_session.json", Path(temp) / "quarantine.json"
            session_file.write_text(json.dumps({"stage": "MAIN", "v2_trace_session_id": "S1", "v2_battery_id": "B1"}))
            app = SimpleNamespace(charge_controller=SimpleNamespace(_v2_trace_session_id="S1", _v2_battery_id="B1"))
            journal = RecoveryQuarantineJournal(journal_file, app)
            journal.persist("ambiguous cold restore")
            app.charge_controller = Controller()  # cold boot: IDLE with no restored identity
            guard = SessionRecoveryGuard(initial_state=RecoveryGuardState(True, "ambiguous cold restore"), durable=True)
            owner = Owner(); port = ExecutionPort(owner, guard); port.bind_guard_owner_lock(GuardExecutionOwnerLock())
            authority = TelegramRecoveryAuthority()
            context = authority.issue(user_id=42, chat_id=42, incident_id=journal.incident_binding()["incident_id"])
            service = OperatorRecoveryClearanceService(execution_port=port, journal=journal,
                operator_authority=authority, session_retirement=_ControllerSessionRetirement(app, str(session_file)))
            result = asyncio.run(service.clear(context))
            self.assertTrue(result.cleared, result.reason)
            self.assertEqual(owner.off_calls, 1)
            tombstone = json.loads(session_file.read_text())
            self.assertEqual((tombstone["state"], tombstone["session_id"], tombstone["battery_id"]), ("retired", "S1", "B1"))
            self.assertFalse(guard.quarantined)
            self.assertFalse(journal.load().quarantined)
            second_boot = Controller()
            ok, message = restore_session(second_boot, 12.0, 0.0, 0.0, session_file=str(session_file))
            self.assertFalse(ok); self.assertIn("retired", message.lower())
            self.assertEqual(second_boot.current_stage, "IDLE")
            self.assertEqual(owner.off_calls, 1)

    def test_cold_boot_identity_failures_are_read_only(self):
        class Controller:
            STAGE_IDLE, STAGE_MAIN, STAGE_MIX = "IDLE", "MAIN", "MIX"
            def __init__(self, **kw): self.current_stage = kw.get("stage", "IDLE"); self._v2_trace_session_id = kw.get("sid"); self._v2_battery_id = kw.get("bid")
            def _clear_restored_targets(self): pass
        valid_binding = {"incident_id": "I1", "session_id": "S1", "battery_id": "B1"}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "session.json"
            provider = lambda controller: _ControllerSessionRetirement(SimpleNamespace(charge_controller=controller), str(path))
            cases = [
                (None, Controller(), valid_binding),
                ("{", Controller(), valid_binding),
                (json.dumps({"stage": "MAIN", "v2_trace_session_id": "S2", "v2_battery_id": "B1"}), Controller(), valid_binding),
                (json.dumps({"stage": "MAIN", "v2_trace_session_id": "S1", "v2_battery_id": "B2"}), Controller(), valid_binding),
                (json.dumps({"stage": "UNKNOWN", "v2_trace_session_id": "S1", "v2_battery_id": "B1"}), Controller(), valid_binding),
                (json.dumps({"stage": "MAIN", "v2_trace_session_id": "S1", "v2_battery_id": "B1"}), Controller(stage="MAIN", sid="OTHER", bid="B1"), valid_binding),
                (json.dumps({"stage": "MAIN", "v2_trace_session_id": "S1", "v2_battery_id": "B1"}), Controller(), {**valid_binding, "battery_id": "B2"}),
            ]
            for contents, controller, binding in cases:
                if contents is None: path.unlink(missing_ok=True)
                else: path.write_text(contents)
                retirement = provider(controller)
                self.assertFalse(retirement.validate(binding))
                if contents is None:
                    self.assertIsNone(retirement.session_id())
                self.assertEqual(retirement.retire("S1", binding=binding,
                    off_evidence=VerifiedOffEvidence("tx", time.monotonic())), None)

    def test_identity_mismatch_and_missing_journal_never_request_off(self):
        class Lock:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
        class Port:
            def __init__(self): self.session_recovery_guard = SimpleNamespace(quarantined=True); self._guard_owner_lock = Lock(); self.calls = 0
            async def request_verified_off_evidence(self): self.calls += 1
        class Authority:
            def authorize_clearance(self, _): return __import__("application.operator_recovery_clearance", fromlist=["AuthorizedRecoveryOperator"]).AuthorizedRecoveryOperator("42")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "session.json"
            app = SimpleNamespace(charge_controller=SimpleNamespace(current_stage="IDLE", STAGE_IDLE="IDLE", STAGE_MAIN="MAIN"))
            path.write_text(json.dumps({"stage": "MAIN", "v2_trace_session_id": "S2", "v2_battery_id": "B1"}))
            retirement = _ControllerSessionRetirement(app, str(path))
            for journal in (
                SimpleNamespace(incident_binding=lambda: {"incident_id": "I1", "session_id": "S1", "battery_id": "B1"}),
                SimpleNamespace(incident_binding=lambda: (_ for _ in ()).throw(ValueError("missing journal"))),
            ):
                port = Port()
                service = OperatorRecoveryClearanceService(execution_port=port, journal=journal,
                    operator_authority=Authority(), session_retirement=retirement)
                result = asyncio.run(service.clear(SimpleNamespace(incident_id="I1")))
                self.assertFalse(result.cleared)
                self.assertEqual(port.calls, 0)

    def test_private_allowlisted_only_allow_all_never_grants(self):
        private = SimpleNamespace(from_user=SimpleNamespace(id=42), chat=SimpleNamespace(id=42, type="private"))
        group = SimpleNamespace(from_user=SimpleNamespace(id=42), chat=SimpleNamespace(id=-10, type="group"))
        spoof = SimpleNamespace(from_user=SimpleNamespace(id=42), chat=SimpleNamespace(id=43, type="private"))
        with patch("runtime.ui.telegram.recovery_clearance.ALLOWED_CHAT_IDS", (42,)):
            self.assertEqual(_approved_private_event(private), (42, 42))
            self.assertIsNone(_approved_private_event(group))
            self.assertIsNone(_approved_private_event(spoof))
        for allow_list in ((), (-1,), (7,)):
            with patch("runtime.ui.telegram.recovery_clearance.ALLOWED_CHAT_IDS", allow_list):
                self.assertIsNone(_approved_private_event(private))

    def test_nonce_is_single_use_expiring_and_user_bound(self):
        authority = TelegramRecoveryAuthority()
        item = authority.issue(user_id=42, chat_id=42, incident_id="incident-X")
        self.assertIsNone(authority.authorize_clearance(item.__class__(item.nonce, 7, 42, "incident-X", item.expires_at)))
        self.assertIsNone(authority.authorize_clearance(item.__class__(item.nonce, 42, 42, "incident-Y", item.expires_at)))
        self.assertEqual(authority.authorize_clearance(item).operator_id, "42")
        self.assertIsNone(authority.authorize_clearance(item))
        expired = authority.issue(user_id=42, chat_id=42, incident_id="incident-X")
        authority.pending[expired.nonce] = expired.__class__(expired.nonce, 42, 42, "incident-X", time.monotonic() - 1)
        self.assertIsNone(authority.authorize_clearance(expired))

    def test_durable_retirement_marker_blocks_restore_and_stage_only_changes_after_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "charge_session.json"
            data = {"stage": "MAIN", "v2_trace_session_id": "S1", "v2_battery_id": "B1"}
            path.write_text(json.dumps(data))
            host = SimpleNamespace(STAGE_IDLE="IDLE", current_stage="MAIN", _v2_trace_session_id="S1",
                                   _v2_battery_id="B1", _clear_restored_targets=lambda: None)
            self.assertFalse(retire_controller_session(host, session_id="S2", battery_id="B1", off_transaction_id="tx", session_file=path))
            self.assertEqual(host.current_stage, "MAIN")
            self.assertTrue(retire_controller_session(host, session_id="S1", battery_id="B1", off_transaction_id="tx", session_file=path))
            self.assertEqual(host.current_stage, "IDLE")
            before = host.current_stage
            ok, message = restore_session(host, 12.0, 0.0, 0.0, session_file=str(path))
            self.assertFalse(ok)
            self.assertIn("retired", message.lower())
            self.assertEqual(host.current_stage, before)

    def test_atomic_retirement_failure_keeps_controller_active(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "charge_session.json"
            path.write_text(json.dumps({"stage": "MIX", "v2_trace_session_id": "S1", "v2_battery_id": "B1"}))
            host = SimpleNamespace(STAGE_IDLE="IDLE", current_stage="MIX", _v2_trace_session_id="S1",
                                   _v2_battery_id="B1", _clear_restored_targets=lambda: None)
            with patch("runtime.charge.persistence.atomic_session_write", side_effect=OSError("fsync")):
                with self.assertRaises(OSError):
                    retire_controller_session(host, session_id="S1", battery_id="B1", off_transaction_id="tx", session_file=path)
            self.assertEqual(host.current_stage, "MIX")

    def test_clearance_off_receipt_requires_fresh_native_register_18(self):
        class Owner:
            def __init__(self, report): self.report = report; self.off_calls = 0; self.reports = 0
            async def turn_off(self):
                self.off_calls += 1
                return True
            async def get_all_live(self):
                raise AssertionError("D087 proof must not use cached live state")
            async def get_native_physical_output_report(self):
                self.reports += 1
                return self.report() if callable(self.report) else self.report

        def native(value=0, *, timestamp=None, age=0.1, native_type="SensorState", status="ok"):
            return value, {"subscription_timestamp_monotonic": time.monotonic() if timestamp is None else timestamp,
                           "age_s": age, "native_type": native_type, "status": status}

        owner = Owner(lambda: native())
        self.assertIsNotNone(asyncio.run(ExecutionPort(owner).request_verified_off_evidence()))
        self.assertEqual((owner.off_calls, owner.reports), (1, 1))

    def test_stale_native_callback_is_rejected_even_when_report_says_recent(self):
        class Owner:
            async def turn_off(self): return True
            async def get_native_physical_output_report(self):
                return 0, {"subscription_timestamp_monotonic": time.monotonic() - 1,
                           "age_s": 0.1, "native_type": "SensorState", "status": "ok"}
        with patch("application.execution_port.NATIVE_OFF_EVIDENCE_TIMEOUT_S", 0):
            self.assertIsNone(asyncio.run(ExecutionPort(Owner()).request_verified_off_evidence()))

    def test_native_off_evidence_rejects_invalid_and_missing_sources(self):
        class Owner:
            async def turn_off(self): return True
            async def get_native_physical_output_report(self): return self.report
        cases = [
            (True, {"native_type": "SensorState", "status": "ok", "age_s": 0.1,
                    "subscription_timestamp_monotonic": time.monotonic()}),
            (0, {"native_type": "BinarySensorState", "status": "ok", "age_s": 0.1,
                 "subscription_timestamp_monotonic": time.monotonic()}),
            (0, {"native_type": "SensorState", "status": "ok", "age_s": 0.1,
                 "subscription_timestamp_monotonic": "bad"}),
        ]
        for report in cases:
            owner = Owner(); owner.report = report
            with patch("application.execution_port.NATIVE_OFF_EVIDENCE_TIMEOUT_S", 0):
                self.assertIsNone(asyncio.run(ExecutionPort(owner).request_verified_off_evidence()))
        class Missing:
            async def turn_off(self): return True
            async def get_all_live(self): return {"output_state_code_v2": 0}
        self.assertIsNone(asyncio.run(ExecutionPort(Missing()).request_verified_off_evidence()))

    def test_off_false_does_not_read_or_issue_another_off(self):
        class Owner:
            def __init__(self): self.off_calls = self.read_calls = 0
            async def turn_off(self): self.off_calls += 1; return False
            async def get_native_physical_output_report(self): self.read_calls += 1
        owner = Owner()
        self.assertIsNone(asyncio.run(ExecutionPort(owner).request_verified_off_evidence()))
        self.assertEqual((owner.off_calls, owner.read_calls), (1, 0))

    def test_evidence_transaction_is_serialized_without_reentrant_deadlock(self):
        class Owner:
            async def turn_off(self): return True
            async def get_native_physical_output_report(self):
                return 0, {"native_type": "SensorState", "status": "ok", "age_s": 0.1,
                           "subscription_timestamp_monotonic": time.monotonic()}
        async def exercise():
            port = ExecutionPort(Owner())
            lock = GuardExecutionOwnerLock()
            port.bind_guard_owner_lock(lock)
            result = await asyncio.wait_for(port.request_verified_off_evidence(), timeout=1)
            self.assertIsNotNone(result)
            self.assertFalse(lock.locked())
        asyncio.run(exercise())


    def test_clearance_reports_off_failure_without_retiring_session(self):
        from application.operator_recovery_clearance import AuthorizedRecoveryOperator
        from types import SimpleNamespace
        class Port:
            session_recovery_guard = SimpleNamespace(quarantined=True)
            last_off_clearance_failure = "turn_off_OutputOffNotConfirmed: no fresh heartbeat"
            _guard_owner_lock = GuardExecutionOwnerLock()
            async def request_verified_off_evidence(self):
                return None
        class Retirement:
            def __init__(self): self.retired = False
            def session_id(self): return "S1"
            def validate(self, binding): return True
            def retire(self, *args, **kwargs):
                self.retired = True
                raise AssertionError("retirement forbidden without OFF receipt")
        class Journal:
            def incident_binding(self):
                return {"session_id": "S1", "battery_id": "B1", "incident_id": "I1"}
        class Authority:
            def authorize_clearance(self, context):
                return AuthorizedRecoveryOperator("operator-1")
        retirement = Retirement()
        service = OperatorRecoveryClearanceService(
            execution_port=Port(), journal=Journal(),
            operator_authority=Authority(), session_retirement=retirement)
        result = asyncio.run(service.clear(SimpleNamespace(incident_id="I1")))
        self.assertFalse(result.cleared)
        self.assertIn("no fresh heartbeat", result.reason)
        self.assertFalse(retirement.retired)



if __name__ == "__main__":
    unittest.main()
