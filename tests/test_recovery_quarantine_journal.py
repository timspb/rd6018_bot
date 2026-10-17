import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from application.session_recovery_guard import SessionRecoveryGuard
from runtime.journal.recovery_quarantine import (
    JOURNAL_NAME, OWNER, RecoveryQuarantineJournal, SCHEMA_VERSION,
)


class RecoveryQuarantineJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / JOURNAL_NAME

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_install_and_cold_restart_remain_quarantined(self):
        journal = RecoveryQuarantineJournal(self.path)
        self.assertFalse(journal.load().quarantined)
        guard = SessionRecoveryGuard(persist_incident=journal.persist, durable=True)
        guard.quarantine("verified_on")
        recreated = SessionRecoveryGuard(
            persist_incident=journal.persist, durable=True,
            initial_state=RecoveryQuarantineJournal(self.path).load(),
        )
        self.assertTrue(recreated.quarantined)
        self.assertEqual(recreated.state.reason, "verified_on")
        self.assertFalse(recreated.operator_rearm(confirmed_output_off=True))

    def test_malformed_unknown_and_wrong_schema_fail_closed(self):
        cases = ["{", json.dumps({"owner": OWNER, "schema_version": 999,
                                  "quarantined": True, "reason": "x", "identity": {}}),
                 json.dumps({"owner": "unknown", "schema_version": SCHEMA_VERSION,
                             "quarantined": True, "reason": "x", "identity": {}})]
        for payload in cases:
            self.path.write_text(payload, encoding="utf-8")
            state = RecoveryQuarantineJournal(self.path).load()
            self.assertTrue(state.quarantined)
            self.assertEqual(state.reason, "invalid_recovery_quarantine_journal")

    def test_identity_is_persisted(self):
        app = SimpleNamespace(charge_controller=SimpleNamespace(
            _v2_trace_session_id="session-A", _v2_battery_id="battery-B"))
        journal = RecoveryQuarantineJournal(self.path, app)
        journal.persist("first")
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(document["identity"], {"session_id": "session-A", "battery_id": "battery-B"})
        self.assertEqual(journal.load().reason, "first")

    def test_failed_write_does_not_release_guard(self):
        path = Path(self.tmp.name) / "missing" / JOURNAL_NAME
        journal = RecoveryQuarantineJournal(path)
        guard = SessionRecoveryGuard(persist_incident=journal.persist, durable=True)
        with self.assertRaises(OSError):
            guard.quarantine("current")
        self.assertTrue(guard.quarantined)


if __name__ == "__main__":
    unittest.main()
