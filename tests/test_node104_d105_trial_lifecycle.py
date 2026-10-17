"""D105: offline-only tests for exact D104 trial states inside D090 owner."""
from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path
import sys
import tarfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from tests.test_node104_d090_transaction import D090TransactionTests, release, TX
from tools import node104_d102_bench_admission as d102


class TrialLifecycleTests(unittest.TestCase):
    setUp_base = D090TransactionTests.setUp
    tearDown = D090TransactionTests.tearDown
    build_venv = D090TransactionTests.build_venv

    def setUp(self):
        self.setUp_base()
        self.service.stable = lambda source: self.service.running and source in (
            release.OLD_SHA, release.SOURCE_SHA, TX.TRIAL_SOURCE_SHA)
        self.tx.trial_socket_ready = lambda: True
        self.tx.trial_edge_proof = self.edge
        self.fixture_pin = self._stage_pin()

    def edge(self):
        return TX.TrialOffProof(time.time(), False, False, 0.0, 900, 0,
                                3.0, 13.57, 0.10, 14.07, 0.20, uuid4().hex)

    def _stage_pin(self):
        rows=[]
        arc=self.staged/"source.tar"
        with tarfile.open(arc,"w") as tar:
            for p in sorted((self.staged/"tree").rglob("*")):
                if p.is_file():
                    name=p.relative_to(self.staged/"tree").as_posix()
                    data=p.read_bytes()
                    member=tarfile.TarInfo(name)
                    member.size=len(data)
                    tar.addfile(member,io.BytesIO(data))
                    rows.append({"path":name,"size":len(data),
                                 "sha256":hashlib.sha256(data).hexdigest()})
        archive_sha=TX.digest(arc)
        manifest={"source_sha":TX.TRIAL_SOURCE_SHA,"node":release.NODE,
                  "service":"rd6018-bot","archive_sha256":archive_sha,"files":rows}
        path=self.staged/"RELEASE_MANIFEST.json"
        path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
        return d102.SourcePin(TX.TRIAL_SOURCE_SHA,archive_sha,TX.digest(path))

    def trial(self,point=None):
        with patch.object(TX,"TRIAL_PIN",self.fixture_pin):
            if point:
                def failpoint(name):
                    if name==point:
                        raise RuntimeError("injected:"+point)
                self.tx.failpoint=failpoint
            return self.tx.begin_trial(self.staged)

    def finish(self):
        with patch.object(TX,"TRIAL_PIN",self.fixture_pin):
            return self.tx.finish_trial()

    def recover(self):
        with patch.object(TX,"TRIAL_PIN",self.fixture_pin):
            return self.tx.recover()

    def assert_old(self, *, backups=True):
        self.assertTrue(self.service.running)
        self.assertEqual(release.OLD_SHA,(self.root/".deploy_sha").read_text().strip())
        self.assertEqual("old-app",(self.root/"app/version").read_text())
        self.assertEqual("old-venv",(self.root/"venv/runtime").read_text())
        self.assertEqual(b"state-stays-byte-identical",(self.root/"state/battery.db").read_bytes())
        self.assertIn("do-not-print-this-secret",(self.root/".env").read_text())
        self.assertEqual("TRIAL_RESTORED",json.loads(self.tx.journal.read_text())["phase"])
        if backups:
            self.assertTrue((self.root/"backups").is_dir())

    def test_full_trial_and_restore_is_never_production_commit(self):
        began=self.trial()
        self.assertEqual("TRIAL_RUNNING",began["phase"])
        self.assertEqual(TX.TRIAL_SCHEMA,began["schema"])
        self.assertEqual(TX.TRIAL_SOURCE_SHA,(self.root/".deploy_sha").read_text().strip())
        self.assertEqual("new-app",(self.root/"app/version").read_text())
        self.assertEqual("isolated-candidate-interpreter",(self.root/"venv/python").read_text())
        self.assertTrue(self.service.running)
        self.assertEqual("TRIAL_RESTORED",self.finish()["phase"])
        self.assert_old()
        self.assertEqual("TRIAL_RESTORED",self.recover()["phase"])

    def test_trial_fault_matrix_recovers_at_all_swaps(self):
        faults=(
            "trial-after-journal-prepared",
            "after-journal-stopped",
            "after-journal-backup_durable",
            "trial-before-swap",
            "trial-after-old-app-rename-before-journal",
            "after-journal-old_app_renamed",
            "trial-after-new-app-rename-before-journal",
            "after-journal-new_app_renamed",
            "trial-after-old-venv-rename-before-journal",
            "after-journal-old_venv_renamed",
            "trial-after-new-venv-rename-before-journal",
            "after-journal-new_venv_renamed",
            "trial-before-start",
            "after-journal-trial_running",
        )
        for name in faults:
            with self.subTest(failpoint=name):
                self.tearDown()
                self.setUp()
                with self.assertRaisesRegex(RuntimeError,"injected:"):
                    self.trial(name)
                self.assert_old()
                self.assertEqual("TRIAL_RESTORED",self.recover()["phase"])

    def test_failed_edge_observer_fails_before_any_stop(self):
        self.tx.trial_edge_proof = None
        with self.assertRaisesRegex(TX.TransactionError,"edge proof"):
            self.trial()
        self.assertEqual(0,self.service.stops)

    def test_no_socket_fails_after_reversible_start(self):
        self.tx.trial_socket_ready=lambda:False
        with self.assertRaisesRegex(TX.TransactionError,"socket"):
            self.trial()
        self.assert_old()

    def test_live_owner_denied_even_with_fake_root(self):
        self.tx.offline=False
        with self.assertRaisesRegex(TX.TransactionError,"not authorized"):
            self.trial()
        self.assertEqual(0,self.service.stops)

    def test_wrong_release_stage_never_stops_old_bot(self):
        (self.staged/"tree/version").write_text("tampered")
        with self.assertRaisesRegex(TX.d102.AdmissionError,"extracted tree"):
            self.trial()
        self.assertEqual(0,self.service.stops)

    def test_stale_autonomous_or_armed_edge_denies_trial(self):
        for changes in (
            {"captured_at_epoch":time.time()-45},
            {"autonomous":True},
            {"lease_armed":True},
            {"lease_remaining_s":5},
            {"lease_ttl_s":30},
            {"protection_code":2},
            {"set_voltage_v":17.0},
            {"modbus_age_s":25.0},
        ):
            with self.subTest(changes=changes):
                self.tx._trial_challenges.clear()
                original=self.edge
                self.tx.trial_edge_proof=lambda c=changes,original=original: original()._replace(**c)
                with self.assertRaises(TX.TransactionError):
                    self.trial()
                self.assertEqual(0,self.service.stops)

    def test_unsafe_edge_after_start_blocks_rollback(self):
        self.trial()
        self.tx.trial_edge_proof=lambda:self.edge()._replace(autonomous=True)
        with self.assertRaisesRegex(TX.TransactionError,"not safe"):
            self.finish()
        self.assertTrue(self.service.running)
        self.assertEqual(TX.TRIAL_SOURCE_SHA,(self.root/".deploy_sha").read_text().strip())
        self.tx.trial_edge_proof=self.edge
        self.assert_old_after_recovery()

    def assert_old_after_recovery(self):
        self.finish()
        self.assert_old()

    def test_recovery_requires_fresh_edge_after_candidate_was_started(self):
        self.trial()
        self.tx.trial_edge_proof = lambda: self.edge()._replace(captured_at_epoch=time.time()-50)
        stops=self.service.stops
        with self.assertRaisesRegex(TX.TransactionError,"stale"):
            self.finish()
        self.assertEqual(stops,self.service.stops)
        self.assertEqual(TX.TRIAL_SOURCE_SHA,(self.root/".deploy_sha").read_text().strip())
        self.tx.trial_edge_proof=self.edge
        self.assertEqual("TRIAL_RESTORED",self.finish()["phase"])
        self.assert_old()

    def test_truncated_backup_before_journal_never_gets_used_for_restore(self):
        self.tx.failpoint=lambda name: (_ for _ in ()).throw(RuntimeError(name)) if name=="after-journal-stopped" else None
        self.tx.trial_edge_proof=self.edge
        with self.assertRaisesRegex(RuntimeError,"after-journal-stopped"):
            self.trial()
        # Crash was safely reversed before backup was written.
        self.assert_old()
        self.assertTrue(json.loads(self.tx.journal.read_text())["rollback_without_backup"])

    def test_prebackup_modified_preimage_prevents_recovery(self):
        def fault(name):
            if name=="after-journal-stopped":
                (self.root/"app/version").write_text("mutated")
                raise RuntimeError("injected after stop")
        self.tx.failpoint=fault
        with self.assertRaisesRegex(TX.TransactionError,"baseline changed"):
            self.trial()
        self.assertFalse(self.service.running)
        self.assertEqual(0,self.service.starts)
        self.assertEqual("STOPPED",json.loads(self.tx.journal.read_text())["phase"])

    def test_trial_source_setpoints_must_remain_unchanged_during_exit(self):
        self.trial()
        self.tx.trial_edge_proof=lambda:self.edge()._replace(set_voltage_v=13.70)
        with self.assertRaisesRegex(TX.TransactionError,"setpoints/protections changed"):
            self.finish()
        self.assertTrue(self.service.running)
        self.tx.trial_edge_proof=self.edge
        self.assertEqual("TRIAL_RESTORED",self.finish()["phase"])

    def test_corrupt_backup_prevents_trial_recovery(self):
        record=self.trial()
        backup=self.root/"backups"/record["backup"]/"app/version"
        backup.write_text("tampered")
        with self.assertRaisesRegex(TX.TransactionError,"backup missing/corrupt"):
            self.finish()
        self.assertEqual(TX.TRIAL_SOURCE_SHA,(self.root/".deploy_sha").read_text().strip())

    def test_invalid_journal_source_rejected_and_no_process_stop(self):
        record=self.trial()
        record["source_sha"]="0"*40
        self.tx.journal.write_text(json.dumps(record))
        stops=self.service.stops
        with self.assertRaisesRegex(TX.TransactionError,"journal identity"):
            self.recover()
        self.assertEqual(stops,self.service.stops)

    def test_restore_fault_is_reentrant_and_idempotent(self):
        self.trial()
        self.tx.failpoint=lambda name: (_ for _ in ()).throw(RuntimeError(name)) if name=="trial-restore-app" else None
        with self.assertRaisesRegex(RuntimeError,"trial-restore-app"):
            self.finish()
        self.assertFalse(self.service.running)
        self.tx.failpoint=lambda _:None
        self.assertEqual("TRIAL_RESTORED",self.recover()["phase"])
        self.assert_old()


if __name__=="__main__":
    unittest.main()
