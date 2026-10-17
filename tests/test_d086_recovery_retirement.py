import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from application.operator_recovery_clearance import (
    AuthorizedRecoveryOperator, OperatorRecoveryClearanceService,
    RetiredControllerSession, VerifiedOffEvidence,
)
from application.session_recovery_guard import RecoveryGuardState, SessionRecoveryGuard
from runtime.journal.recovery_quarantine import OWNER, RecoveryQuarantineJournal


class Lock:
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False


class Authority:
    def __init__(self, result): self.result = result
    def authorize_clearance(self, context): return self.result


class Retirement:
    def __init__(self, result=True):
        self.result, self.calls = result, []
    def session_id(self): return "session-A"
    def retire(self, session_id):
        self.calls.append(session_id)
        return RetiredControllerSession(session_id) if self.result else False


class Port:
    def __init__(self, guard, evidence=None, raises=False):
        self.session_recovery_guard, self._guard_owner_lock = guard, Lock()
        self.evidence, self.raises, self.calls = evidence, raises, 0
    async def request_verified_off(self):
        self.calls += 1
        if self.raises: raise RuntimeError("OFF failed")
        return self.evidence


class RecoveryRetirementJournalTests(unittest.TestCase):
    def incident(self, path, *, identity=None, incident_id="incident-A"):
        doc = {"owner": OWNER, "schema_version": 1, "quarantined": True,
               "reason": "ambiguous restore", "incident_utc": "2026-10-17T00:00:00+00:00",
               "incident_id": incident_id,
               "identity": identity if identity is not None else {"session_id": "session-A", "battery_id": "battery-A"}}
        path.write_text(json.dumps(doc))
        return doc

    def test_retire_requires_valid_matching_incident_and_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "q.json"
            journal = RecoveryQuarantineJournal(path)
            for invalid in (None, "{", json.dumps({"owner": OWNER, "schema_version": 8})):
                if invalid is None: path.unlink(missing_ok=True)
                else: path.write_text(invalid)
                with self.assertRaises(ValueError):
                    journal.retire(operator_id="op", session_id="session-A", confirmed_off_evidence="off-1")
            for identity, sid in (({}, "session-A"), ({"session_id": "old"}, "session-A"), ({"battery_id": "battery-A"}, "session-A")):
                self.incident(path, identity=identity)
                with self.assertRaises(ValueError):
                    journal.retire(operator_id="op", session_id=sid, confirmed_off_evidence="off-1")
            original = self.incident(path)
            with self.assertRaises(ValueError):
                journal.retire(operator_id="op", session_id="other", confirmed_off_evidence="off-1")
            self.assertEqual(json.loads(path.read_text()), original)
            journal.retire(operator_id="op", session_id="session-A", confirmed_off_evidence="off-tx-1")
            tombstone = json.loads(path.read_text())
            self.assertEqual(tombstone["retirement"]["incident_id"], "incident-A")
            self.assertEqual(tombstone["retirement"]["incident_reason"], "ambiguous restore")
            self.assertEqual(tombstone["retirement"]["battery_id"], "battery-A")
            self.assertFalse(journal.load().quarantined)

    def test_tombstone_unknown_fields_and_missing_provenance_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "q.json"
            journal = RecoveryQuarantineJournal(path)
            valid = {"owner": OWNER, "schema_version": 2, "state": "retired", "quarantined": False,
                     "retirement": {"operator_id": "op", "session_id": "s", "confirmed_off_evidence": "off",
                                    "retired_utc": "now", "incident_id": "i", "incident_reason": "why", "battery_id": None}}
            for mutate in (lambda d: d.update(extra="x"),
                           lambda d: d["retirement"].pop("incident_id"),
                           lambda d: d["retirement"].update(incident_reason=" ")):
                doc = json.loads(json.dumps(valid)); mutate(doc); path.write_text(json.dumps(doc))
                self.assertTrue(journal.load().quarantined)


class ClearanceServiceTests(unittest.TestCase):
    def make(self, *, authority=None, retirement=True, evidence=None, raises=False, journal=None):
        guard = SessionRecoveryGuard(initial_state=RecoveryGuardState(True, "incident"), durable=True)
        port = Port(guard, evidence, raises)
        retire = Retirement(retirement)
        service = OperatorRecoveryClearanceService(execution_port=port,
            journal=journal or SimpleNamespace(retire=lambda **kwargs: None),
            operator_authority=authority, session_retirement=retire)
        return service, guard, port, retire

    def call(self, service, context=object()): return asyncio.run(service.clear(context))

    def test_rejections_precede_hardware_for_authority_or_retirement_gap(self):
        service, guard, port, retire = self.make(authority=None, evidence=VerifiedOffEvidence("x", time.monotonic()))
        self.assertFalse(self.call(service).cleared); self.assertEqual(port.calls, 0); self.assertTrue(guard.quarantined)
        service, guard, port, retire = self.make(authority=Authority(AuthorizedRecoveryOperator("op")), retirement=None)
        service._retire_session = None
        self.assertFalse(self.call(service).cleared); self.assertEqual(port.calls, 0)
        service, guard, port, retire = self.make(authority=Authority(True), evidence=VerifiedOffEvidence("x", time.monotonic()))
        self.assertFalse(self.call(service).cleared); self.assertEqual(port.calls, 0)

    def test_verified_off_failure_and_stale_or_untyped_evidence_fail_closed(self):
        auth = Authority(AuthorizedRecoveryOperator("op"))
        for evidence, raises in ((None, True), ("arbitrary string", False),
                                 (VerifiedOffEvidence("stale", time.monotonic() - 60), False)):
            service, guard, port, retire = self.make(authority=auth, evidence=evidence, raises=raises)
            self.assertFalse(self.call(service).cleared)
            self.assertTrue(guard.quarantined); self.assertEqual(retire.calls, [])

    def test_retirement_failure_and_journal_failure_keep_guard_latched(self):
        auth = Authority(AuthorizedRecoveryOperator("op")); proof = VerifiedOffEvidence("tx", time.monotonic())
        service, guard, port, retire = self.make(authority=auth, retirement=False, evidence=proof)
        self.assertFalse(self.call(service).cleared); self.assertTrue(guard.quarantined)
        def fail(**kwargs): raise OSError("disk")
        service, guard, port, retire = self.make(authority=auth, evidence=proof, journal=SimpleNamespace(retire=fail))
        self.assertFalse(self.call(service).cleared); self.assertEqual(retire.calls, ["session-A"]); self.assertTrue(guard.quarantined)

    def test_success_stages_off_retirement_tombstone_then_ram_release(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = RecoveryQuarantineJournal(Path(directory) / "q.json")
            journal = RecoveryQuarantineJournal(Path(directory) / "q.json",
                SimpleNamespace(charge_controller=SimpleNamespace(_v2_trace_session_id="session-A", _v2_battery_id="battery-A")))
            journal.persist("incident")
            service, guard, port, retire = self.make(authority=Authority(AuthorizedRecoveryOperator("op")),
                evidence=VerifiedOffEvidence("tx", time.monotonic()), journal=journal)
            result = self.call(service)
            self.assertTrue(result.cleared)
            self.assertEqual(retire.calls, ["session-A"])
            self.assertFalse(guard.quarantined)
            self.assertFalse(journal.load().quarantined)
            # Simulate the ordered controller-owned retirement surviving cold boot.
            retired_controller_sessions = {"session-A"}
            self.assertIn(json.loads(journal.path.read_text())["retirement"]["session_id"], retired_controller_sessions)


if __name__ == "__main__": unittest.main()
