import json
import tempfile
import unittest
from pathlib import Path
from tools.node104_d090_transaction import digest, inventory
from tools.d144_state_preserving_transition import OwnerTransition, TransitionError, transaction_slot

class FakeService:
    def __init__(self): self.running=True; self.stops=0
    def active(self): return self.running
    def main_pid(self): return 123 if self.running else 0
    def stop(self): self.running=False; self.stops+=1
    def start(self): self.running=True
    def stable(self): return self.running

class D144Tests(unittest.TestCase):
    def test_engine_has_separate_journal(self):
        self.assertEqual(__import__("tools.d144_state_preserving_transition",fromlist=["JOURNAL"]).JOURNAL,"D144_TRANSACTION.json")

    def test_stub(self):
        self.assertTrue(True)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.candidate=self.root/"candidate"
        for p in ("app","venv","state","candidate/app","candidate/venv"):
            (self.root/p).mkdir(parents=True)
        for p,v in (("app/x","old"),("venv/x","old"),("candidate/app/x","new"),("candidate/venv/x","new"),("state/session","RETIRED"),("D090_TRANSACTION.json",'{"phase":"STARTED"}'),(".deploy_sha","legacy")):
            (self.root/p).write_text(v)

        self.old={p:inventory(self.root/p) for p in ("app","venv")}
        self.new={p:inventory(self.candidate/p) for p in ("app","venv")}
        self.service=FakeService()

    def proof(self, *, require_stopped):
        if require_stopped and self.service.main_pid()!=0:
            raise TransitionError('service unexpectedly active')

    def tx(self, failpoint=None):
        return OwnerTransition(self.root, self.service, candidate=self.candidate,
            evidence=self.proof, expected_before=self.old, expected_candidate=self.new,
            legacy_journal_sha256=digest(self.root/'D090_TRANSACTION.json'),
            candidate_stable=self.service.stable, restored_stable=self.service.stable,
            release_identity={'schema':'D144_RELEASE_IDENTITY_V1','source_sha':'d351c208cbf8666f881a4660df6a0b211170e857','candidate_identity_sha256':'a'*64},
            failpoint=failpoint)

    def tx_slot(self, slot, candidate, failpoint=None):
        journal=self.root/("D144_TRANSACTION.json" if slot==1 else f"D144_TRANSACTION_{slot}.json")
        if journal.is_file():
            recorded=json.loads(journal.read_text())
            before,wanted=recorded["before"],recorded["candidate"]
        else:
            before={p:inventory(self.root/p) for p in ("app","venv")}
            wanted={p:inventory(candidate/p) for p in ("app","venv")}
        return OwnerTransition(self.root,self.service,candidate=candidate,
            evidence=self.proof,expected_before=before,expected_candidate=wanted,
            legacy_journal_sha256=digest(self.root/'D090_TRANSACTION.json'),
            candidate_stable=self.service.stable,restored_stable=self.service.stable,
            release_identity={'schema':'D144_RELEASE_IDENTITY_V1','source_sha':'a351c208cbf8666f881a4660df6a0b211170e857','candidate_identity_sha256':'b'*64},
            failpoint=failpoint,slot=slot)

    def test_cutover_preserves_state(self):
        self.assertEqual(self.tx().run()['phase'],'COMMITTED')
        self.assertEqual((self.root/'app/x').read_text(),'new')
        self.assertEqual((self.root/'state/session').read_text(),'RETIRED')
        self.assertEqual((self.root/'.deploy_sha').read_text(),'legacy')
        marker=json.loads((self.root/'D144_INSTALLED_RELEASE.json').read_text())
        self.assertEqual(marker['source_sha'],'d351c208cbf8666f881a4660df6a0b211170e857')

    def test_repeated_upgrade_appends_history_and_keeps_each_rollback(self):
        first=self.tx().run()
        old_journal=(self.root/'D144_TRANSACTION.json').read_bytes()
        old_identity=(self.root/'D144_INSTALLED_RELEASE.json').read_bytes()
        old_backup={n:inventory(self.root/'d144-backup'/n) for n in ('app','venv')}
        candidate=self.root/'candidate-2'
        for part in ('app','venv'):
            (candidate/part).mkdir(parents=True)
            (candidate/part/'x').write_text('release-2')
        self.assertEqual(transaction_slot(self.root),2)
        record=self.tx_slot(2,candidate).run()
        self.assertEqual(record['phase'],'COMMITTED')
        self.assertEqual((self.root/'app/x').read_text(),'release-2')
        self.assertEqual((self.root/'D144_TRANSACTION.json').read_bytes(),old_journal)
        self.assertEqual((self.root/'D144_INSTALLED_RELEASE.json').read_bytes(),old_identity)
        self.assertEqual({n:inventory(self.root/'d144-backup'/n) for n in ('app','venv')},old_backup)
        self.assertTrue((self.root/'d144-backup-2').is_dir())
        self.assertEqual(transaction_slot(self.root),3)

    def test_repeated_upgrade_crash_restores_previous_release_and_preserves_history(self):
        self.tx().run()
        old_journal=(self.root/'D144_TRANSACTION.json').read_bytes()
        candidate=self.root/'candidate-2'
        for part in ('app','venv'):
            (candidate/part).mkdir(parents=True)
            (candidate/part/'x').write_text('release-2')
        def crash(point):
            if point=='AFTER_NEW_APP_RENAME_BEFORE_JOURNAL': raise RuntimeError('power loss')
        with self.assertRaisesRegex(RuntimeError,'power loss'):
            self.tx_slot(2,candidate,crash).run()
        state=(self.root/'state/session').read_text()
        recovered=self.tx_slot(2,candidate).recover()
        self.assertEqual(recovered['phase'],'RESTORED')
        self.assertEqual((self.root/'app/x').read_text(),'new')
        self.assertEqual((self.root/'D144_TRANSACTION.json').read_bytes(),old_journal)
        self.assertEqual((self.root/'state/session').read_text(),state)
        self.assertEqual(transaction_slot(self.root),3)

    def test_realistic_legacy_started_journal_does_not_block_owner_transition(self):
        legacy = self.root / "D090_TRANSACTION.json"
        legacy.write_text(json.dumps({
            "schema": 1,
            "phase": "STARTED",
            "source_sha": "930239c670899e14ccb09154d99baf77df90da10",
            "transaction": "818df047a6e64a22905d6da900162a86",
        }))
        self.assertEqual((self.root / ".deploy_sha").read_text(), "legacy")
        before_legacy = legacy.read_bytes()
        self.assertEqual(self.tx().run()["phase"], "COMMITTED")
        self.assertEqual(legacy.read_bytes(), before_legacy)
        self.assertEqual((self.root / ".deploy_sha").read_text(), "legacy")
        self.assertEqual((self.root / "state" / "session").read_text(), "RETIRED")

    def test_drift_rejected_before_stop(self):
        (self.root/'app/x').write_text('drift')
        with self.assertRaises(TransitionError):self.tx().run()
        self.assertEqual(self.service.stops,0)

    def test_crash_restore_preserves_new_state(self):
        def crash(phase):
            if phase=='AFTER_NEW_APP_RENAME_BEFORE_JOURNAL':
                raise RuntimeError('crash')
        with self.assertRaises(RuntimeError):self.tx(crash).run()
        (self.root/'state/session').write_text('RETIRED updated')
        self.assertEqual(self.tx().recover()['phase'],'RESTORED')
        self.assertEqual(inventory(self.root/'app'),self.old['app'])
        self.assertEqual(inventory(self.root/'venv'),self.old['venv'])
        self.assertEqual((self.root/'state/session').read_text(),'RETIRED updated')

    def test_crash_boundaries(self):
        points=('BACKUP_DURABLE','STOPPED','OLD_APP_RENAMED',
                'NEW_APP_RENAMED','OLD_VENV_RENAMED',
                'NEW_VENV_RENAMED','STARTED')
        for point in points:
            with self.subTest(point=point):
                self.setUp()
                def fail(label):
                    if label==point:raise RuntimeError('crash')
                with self.assertRaises(RuntimeError):self.tx(fail).run()
                self.assertEqual(self.tx().recover()['phase'],'RESTORED')
                for name in ('app','venv'):
                    self.assertEqual(inventory(self.root/name),self.old[name])

    def test_crash_between_identity_and_commit_restores_marker(self):
        def fail(point):
            if point=='AFTER_IDENTITY_BEFORE_COMMIT':
                raise RuntimeError('crash before commit')
        with self.assertRaisesRegex(RuntimeError,'crash'):
            self.tx(fail).run()
        self.assertTrue((self.root/'D144_INSTALLED_RELEASE.json').is_file())
        (self.root/'state/session').write_text('RETIRED updated')
        self.assertEqual(self.tx().recover()['phase'],'RESTORED')
        self.assertFalse((self.root/'D144_INSTALLED_RELEASE.json').exists())
        self.assertEqual((self.root/'state/session').read_text(),'RETIRED updated')

    def test_unexpected_identity_rejected_before_stop(self):
        (self.root/'D144_INSTALLED_RELEASE.json').write_text('{}')
        with self.assertRaises(TransitionError):
            self.tx().run()
        self.assertEqual(self.service.stops,0)

    def test_prepared_crash_before_backup_settles_without_stop(self):
        def crash(point):
            if point == 'PREPARED':
                raise RuntimeError('injected')
        with self.assertRaises(RuntimeError):
            self.tx(crash).run()
        stops = self.service.stops
        self.assertEqual(self.tx().recover()['phase'], 'RESTORED')
        self.assertEqual(self.service.stops, stops)
        self.assertEqual(inventory(self.root/'app'), self.old['app'])
        self.assertEqual(inventory(self.root/'venv'), self.old['venv'])

    def test_prepared_crash_drift_refuses_without_stop(self):
        def crash(point):
            if point == 'PREPARED':
                raise RuntimeError('injected')
        with self.assertRaises(RuntimeError):
            self.tx(crash).run()
        (self.root/'app/x').write_text('unexpected')
        stops = self.service.stops
        with self.assertRaises(TransitionError):
            self.tx().recover()
        self.assertEqual(self.service.stops, stops)

    def test_prepared_crash_stopped_service_refuses(self):
        def crash(point):
            if point == 'PREPARED':
                raise RuntimeError('injected')
        with self.assertRaises(RuntimeError):
            self.tx(crash).run()
        self.service.stop()
        stops = self.service.stops
        with self.assertRaises(TransitionError):
            self.tx().recover()
        self.assertEqual(self.service.stops, stops)
