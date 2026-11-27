"""B1059: exact pending START + durable incident retired by existing operator owner."""
import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path

from application.controller_session_retirement import _ControllerSessionRetirement
from application.execution_port import ExecutionPort
from application.guard_execution_owner_lock import GuardExecutionOwnerLock
from application.operator_recovery_clearance import OperatorRecoveryClearanceService
from application.session_recovery_guard import SessionRecoveryGuard, RecoveryGuardState
from runtime.charge.persistence import begin_start_pending, read_start_pending
from runtime.journal.recovery_quarantine import RecoveryQuarantineJournal
from runtime.ui.telegram.recovery_clearance import TelegramRecoveryAuthority


class _Controller:
    STAGE_IDLE = "IDLE"
    STAGE_MAIN = "Main Charge"
    STAGE_MIX = "Mix Mode"

    def __init__(self, session_id=None, battery_id=None):
        self.current_stage = self.STAGE_IDLE
        self._v2_trace_session_id = session_id
        self._v2_battery_id = battery_id
        self._recovery_session_retirement_pending = False
        self._recovery_session_retired_id = None
        self._guarded_restore_candidate = None


class _OutputOwner:
    def __init__(self):
        self.off_calls = 0
        self.on_calls = 0
        self.last_off_at = None

    async def turn_off(self):
        self.off_calls += 1
        self.last_off_at = time.monotonic()
        return True

    async def turn_on(self):
        self.on_calls += 1
        raise AssertionError("recovery must not energize Output")

    async def get_native_physical_output_report(self):
        return 0.0, {
            "native_type": "SensorState", "status": "ok", "age_s": 0.1,
            "subscription_timestamp_monotonic": time.monotonic(),
        }


class _App:
    def __init__(self):
        self.charge_controller = _Controller("S-PENDING", "Leoch_72Ah")


class PendingClearanceTests(unittest.IsolatedAsyncioTestCase):
    def make_case(self, directory, *, previous=False, reason="start_enable_off_receipt_invalid"):
        path = Path(directory) / "charge_session.json"
        journal_path = Path(directory) / "quarantine.json"
        app = _App()
        journal = RecoveryQuarantineJournal(journal_path, app)
        journal.persist(reason)
        if previous:
            path.write_text('{"stage":"DONE","start_transaction_generation":3}')
        pending = begin_start_pending({
            "stage": "Main Charge", "v2_trace_session_id": "S-PENDING",
            "v2_battery_id": "Leoch_72Ah", "output_intent": "on",
        }, transaction_id="b1059-test", path=path)
        assert pending.status.value == "COMMITTED"
        # Cold reboot: no in-memory managed session.
        app.charge_controller = _Controller()
        app.recovery_quarantine_journal = journal
        guard = SessionRecoveryGuard(initial_state=RecoveryGuardState(True, reason), durable=True)
        owner = _OutputOwner()
        port = ExecutionPort(owner, guard)
        port.bind_guard_owner_lock(GuardExecutionOwnerLock())
        app.execution_port = port
        authority = TelegramRecoveryAuthority()
        service = OperatorRecoveryClearanceService(
            execution_port=port, journal=journal, operator_authority=authority,
            session_retirement=_ControllerSessionRetirement(app, str(path)),
        )
        def ticket():
            return authority.issue(user_id=42, chat_id=42,
                                   incident_id=journal.incident_binding()["incident_id"])
        return path, journal, port, owner, service, ticket

    async def test_exact_pending_and_off_evidence_retire_both_owners(self):
        with tempfile.TemporaryDirectory() as temp:
            path, journal, port, owner, service, ticket = self.make_case(temp)
            result = await service.clear(ticket())
            self.assertTrue(result.cleared, result.reason)
            self.assertFalse(path.exists())
            self.assertEqual(owner.off_calls, 1)
            self.assertEqual(owner.on_calls, 0)
            self.assertFalse(port.session_recovery_guard.quarantined)
            self.assertFalse(journal.load().quarantined)
            self.assertEqual(journal.retirement_binding()["session_id"], "S-PENDING")

    async def test_missing_journal_tombstone_after_pending_rollback_can_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            path, journal, port, owner, service, ticket = self.make_case(temp)
            original = journal.retire
            def fail_retire(**kwargs):
                raise OSError("simulated journal persistence failure")
            journal.retire = fail_retire
            failed = await service.clear(ticket())
            self.assertFalse(failed.cleared)
            self.assertEqual(failed.reason, "durable_retirement_failed")
            self.assertFalse(path.exists())
            self.assertTrue(port.session_recovery_guard.quarantined)
            journal.retire = original
            recovered = await service.clear(ticket())
            self.assertTrue(recovered.cleared, recovered.reason)
            self.assertEqual(owner.off_calls, 2)
            self.assertFalse(port.session_recovery_guard.quarantined)

    async def test_prior_committed_session_is_never_retired_by_pending_shortcut(self):
        with tempfile.TemporaryDirectory() as temp:
            path, _journal, _port, owner, service, ticket = self.make_case(temp, previous=True)
            before = path.read_bytes()
            rejected = await service.clear(ticket())
            self.assertFalse(rejected.cleared)
            self.assertEqual(owner.off_calls, 0)
            self.assertEqual(path.read_bytes(), before)

    async def test_unrelated_durable_incident_never_activates_pending_retirement(self):
        with tempfile.TemporaryDirectory() as temp:
            path, _journal, _port, owner, service, ticket = self.make_case(
                temp, reason="different_incident"
            )
            before = path.read_bytes()
            rejected = await service.clear(ticket())
            self.assertFalse(rejected.cleared)
            self.assertEqual(owner.off_calls, 0)
            self.assertEqual(path.read_bytes(), before)
