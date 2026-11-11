"""A retired previous Guard may be released only on matching verified-OFF tombstone."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from application.start_transaction_service import retire_previous_guard_for_start

class RetiredGuardStartTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"charge_session.json"
        self.guard=SimpleNamespace(session_id="old-session",battery_id="old-battery")
        self.owner=SimpleNamespace(_main_current_guard=self.guard,_main_current_guard_revision=8)
        self.doc={"owner":"runtime.charge.persistence","schema_version":1,
                  "state":"retired","stage":"RETIRED",
                  "retirement_kind":"operator_recovery_clearance",
                  "output_intent":"verified_off",
                  "verified_off_transaction_id":"receipt",
                  "session_id":"old-session","battery_id":"old-battery"}
    def test_exact_retirement_releases_old_memory(self):
        self.path.write_text(json.dumps(self.doc))
        self.assertTrue(retire_previous_guard_for_start(self.owner,session_file=self.path))
        self.assertIsNone(self.owner._main_current_guard)
        self.assertIsNone(self.owner._main_current_guard_revision)
    def test_active_or_foreign_tombstones_do_not_release(self):
        for key,value in (("state","running"),("session_id","other"),
                          ("battery_id","other"),("output_intent","unknown"),
                          ("verified_off_transaction_id",None)):
            with self.subTest(key=key):
                self.path.write_text(json.dumps({**self.doc,key:value}))
                self.assertFalse(retire_previous_guard_for_start(self.owner,session_file=self.path))
                self.assertIs(self.owner._main_current_guard,self.guard)
        self.path.unlink()
        self.assertFalse(retire_previous_guard_for_start(self.owner,session_file=self.path))
    def test_missing_session_accepts_exact_retired_quarantine_journal(self):
        quarantine=Path(self.temp.name)/"session_recovery_quarantine.json"
        journal={"owner":"runtime.charge.recovery_quarantine_journal",
                 "schema_version":2,"state":"retired","quarantined":False,
                 "retirement":{"session_id":"old-session","battery_id":"old-battery",
                               "confirmed_off_evidence":"independent-off-proof"}}
        quarantine.write_text(json.dumps(journal))
        self.assertTrue(retire_previous_guard_for_start(
            self.owner,session_file=self.path,quarantine_file=quarantine))
        self.assertIsNone(self.owner._main_current_guard)

    def test_missing_session_rejects_uncleared_or_wrong_quarantine(self):
        quarantine=Path(self.temp.name)/"session_recovery_quarantine.json"
        base={"owner":"runtime.charge.recovery_quarantine_journal",
              "schema_version":2,"state":"retired","quarantined":False,
              "retirement":{"session_id":"old-session","battery_id":"old-battery",
                            "confirmed_off_evidence":"receipt"}}
        for change in ({"quarantined":True},{"state":"active"},
                       {"retirement":{**base["retirement"],"session_id":"other"}}):
            quarantine.write_text(json.dumps({**base,**change}))
            self.assertFalse(retire_previous_guard_for_start(
                self.owner,session_file=self.path,quarantine_file=quarantine))
            self.assertIs(self.owner._main_current_guard,self.guard)

    def test_absent_memory_needs_no_retirement(self):
        self.owner._main_current_guard=None
        self.assertTrue(retire_previous_guard_for_start(self.owner,session_file=self.path))
