from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import node104_d090_release as release

SPEC = importlib.util.spec_from_file_location('node104_d090_transaction', ROOT / 'tools/node104_d090_transaction.py')
TX = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(TX)


class FakeService:
    def __init__(self):
        self.running = True
        self.starts = 0
        self.stops = 0
        self.stable_sha = None

    def active(self): return self.running
    def main_pid(self): return 321 if self.running else 0
    def stop(self): self.running = False; self.stops += 1
    def start(self): self.running = True; self.starts += 1
    def stable(self, expected_sha):
        return self.running and expected_sha in (release.SOURCE_SHA, release.OLD_SHA)


class D090TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='node104-fake-')
        self.root = Path(self.temp.name) / 'node104-fake-root'
        self.root.mkdir()
        for name in ('app', 'state', 'venv', 'backups'):
            (self.root / name).mkdir()
        (self.root / 'app' / 'version').write_text('old-app')
        (self.root / 'state' / 'battery.db').write_bytes(b'state-stays-byte-identical')
        (self.root / 'venv' / 'runtime').write_text('old-venv')
        (self.root / '.env').write_text('TOKEN=do-not-print-this-secret\n')
        (self.root / '.deploy_sha').write_text(release.OLD_SHA + '\n')
        (self.root / 'service.unit').write_text('ExecStart=/opt/services/rd6018-bot/venv/bin/python /opt/services/rd6018-bot/app/bot.py\n')
        self.staged = self.root / 'staged'
        (self.staged / 'tree').mkdir(parents=True)
        (self.staged / 'tree' / 'version').write_text('new-app')
        (self.staged / 'tree' / 'requirements.txt').write_text('')
        self.service = FakeService()
        self.now = time.time()
        self.proof_counter = 0

        def proof():
            self.proof_counter += 1
            return release.PhysicalOffProof(time.time(), release.MACHINE_ID, self.service.main_pid(),
                True, 0.0, 0.0, True, 0.0, 0.0, True, False, False, 1, False,
                (f'ha:{self.proof_counter}', f'esp:{self.proof_counter}'))

        self.tx = TX.D090Transaction(self.root, service=self.service, proof=proof,
            host_check=lambda: None, acceptance=lambda: None, venv_builder=self.build_venv,
            space_check=lambda _: None, candidate_validate=lambda *_: None, offline=True)
        self.proof = proof

    def tearDown(self): self.temp.cleanup()

    def build_venv(self, path: Path, app: Path):
        path.mkdir()
        (path / 'python').write_text('isolated-candidate-interpreter')
        self.assertFalse((self.root / 'venv' / 'python').exists())

    def _run(self, *, failpoint=None):
        self.service.stable_sha = release.SOURCE_SHA
        if failpoint:
            def inject(point):
                if point == failpoint:
                    raise RuntimeError('injected fault at ' + point)
            self.tx.failpoint = inject
        with patch.object(release, 'verify_staged_release', return_value={'source_sha': release.SOURCE_SHA}), \
             patch.object(release, 'validate_physical_acceptance', return_value=None):
            prepared = self.tx.prepare(self.staged, acceptance_record={}, evidence_dir=self.root)
            return self.tx.activate(self.staged, acceptance_record={}, evidence_dir=self.root, prepared=prepared)

    def _started_journal(self):
        baseline = self.tx._baseline()
        ident = '818df047a6e64a22905d6da900162a86'
        backup = self.root / 'backups' / ('d090-' + ident)
        backup.mkdir()
        for name in ('app', 'state', 'venv'):
            import shutil
            shutil.copytree(self.root / name, backup / name, symlinks=True)
        for name in ('.env', TX.MARKER):
            import shutil
            shutil.copy2(self.root / name, backup / name)
        import shutil
        shutil.copy2(self.root / 'service.unit', backup / 'service.unit')
        (self.root / 'app' / 'version').write_text('candidate-app')
        (self.root / 'venv' / 'runtime').write_text('candidate-venv')
        record = {'schema': 1, 'node': release.NODE, 'source_sha': release.SOURCE_SHA,
                  'old_sha': release.OLD_SHA, 'transaction': ident, 'phase': 'STARTED',
                  'candidate': 'candidate-' + ident, 'backup': backup.name,
                  'candidate_inventory': {'app': TX.inventory(self.root / 'app'),
                                          'venv': TX.inventory(self.root / 'venv')},
                  'baseline': baseline, 'backup_inventory': TX.inventory(backup)}
        TX._atomic_json(self.tx.journal, record)
        return record

    def _software_recovery_executor(self):
        def proof():
            self.proof_counter += 1
            return release.PhysicalOffProof(
                time.time(), release.MACHINE_ID, self.service.main_pid(), True,
                0.0, 0.0, True, 0.0, 0.0, True, False, False, 1, True,
                (f'recovery-ha:{self.proof_counter}', f'recovery-esp:{self.proof_counter}'))
        self.tx = TX.D090Transaction(
            self.root, service=self.service, proof=proof, host_check=lambda: None,
            acceptance=lambda: None, venv_builder=self.build_venv,
            space_check=lambda _: None, candidate_validate=lambda *_: None,
            offline=True, software_release=True, pinned=release.PINNED,
            preimage_inventory_sha256='a' * 64,
            release_admission=lambda: None)
        return self.tx

    def test_software_recovery_preserves_current_session_and_d084_quarantine(self):
        self._started_journal()
        session = self.root / 'state' / 'charge_session.json'
        quarantine = self.root / 'state' / 'session_recovery_quarantine.json'
        session.write_text('{"session_id":"e18eb85-current","stage":"Main Charge","state":"active"}\n')
        quarantine.write_text('{"owner":"runtime.charge.recovery_quarantine_journal","schema_version":1,"quarantined":true,"incident_id":"b6b90c17","reason":"D084 active","identity":{"session_id":"e18eb85-current"}}\n')
        live_state_before = TX.inventory(self.root / 'state')

        result = self._software_recovery_executor().recover()

        self.assertEqual('ROLLED_BACK', result['phase'])
        self.assertEqual('old-app', (self.root / 'app' / 'version').read_text())
        self.assertEqual('old-venv', (self.root / 'venv' / 'runtime').read_text())
        self.assertEqual(live_state_before, TX.inventory(self.root / 'state'))
        self.assertIn('e18eb85-current', session.read_text())
        self.assertIn('b6b90c17', quarantine.read_text())
        self.assertEqual(live_state_before, result['recovery_state_inventory'])
        self.assertEqual((1, 1), (self.service.stops, self.service.starts))

    def test_software_recovery_uses_distinct_pre_stop_stopped_and_post_start_proofs(self):
        self._started_journal()
        (self.root / 'state' / 'charge_session.json').write_text(
            '{"session_id":"e18eb85-current","stage":"Main Charge","state":"active"}\n')
        (self.root / 'state' / 'session_recovery_quarantine.json').write_text(
            '{"owner":"runtime.charge.recovery_quarantine_journal","schema_version":1,"quarantined":true,"incident_id":"b6b90c17","reason":"D084 active","identity":{"session_id":"e18eb85-current"}}\n')
        tx = self._software_recovery_executor()
        events = []
        original_proof, original_stop, original_start = tx.proof, self.service.stop, self.service.start
        def proof():
            events.append(('proof', self.service.running))
            return original_proof()
        def stop():
            events.append(('stop', self.service.running))
            original_stop()
        def start():
            events.append(('start', self.service.running))
            original_start()
        tx.proof, self.service.stop, self.service.start = proof, stop, start

        tx.recover()

        self.assertEqual(['proof', 'stop', 'proof', 'proof', 'start', 'proof'],
                         [event[0] for event in events])
        self.assertEqual([True, True, False, False, False, True],
                         [event[1] for event in events])

    def test_software_recovery_refuses_unstable_running_owner_before_stop(self):
        self._started_journal()
        tx = self._software_recovery_executor()
        tx.service.stable = lambda _: False
        with self.assertRaisesRegex(TX.TransactionError, 'not positively stable'):
            tx.recover()
        self.assertTrue(self.service.running)
        self.assertEqual((0, 0), (self.service.stops, self.service.starts))

    def test_software_recovery_refuses_stale_or_unsafe_proof_before_stop(self):
        self._started_journal()
        tx = self._software_recovery_executor()
        valid = tx.proof()
        tx.proof = lambda: replace(valid, captured_at_epoch=time.time() - 45)
        journal_before = tx.journal.read_bytes()
        with self.assertRaisesRegex(release.GateError, 'expired'):
            tx.recover()
        self.assertEqual((0, 0), (self.service.stops, self.service.starts))
        self.assertTrue(self.service.running)
        self.assertEqual(journal_before, tx.journal.read_bytes())

        tx.proof = lambda: replace(valid, esp128_output_off=False)
        with self.assertRaisesRegex(release.GateError, 'OFF proof'):
            tx.recover()
        self.assertEqual((0, 0), (self.service.stops, self.service.starts))
        self.assertTrue(self.service.running)

    def test_software_recovery_refuses_state_drift_after_durable_snapshot(self):
        self._started_journal()
        (self.root / 'state' / 'charge_session.json').write_text(
            '{"session_id":"e18eb85-current","stage":"Main Charge","state":"active"}\n')
        (self.root / 'state' / 'session_recovery_quarantine.json').write_text(
            '{"owner":"runtime.charge.recovery_quarantine_journal","schema_version":1,"quarantined":true,"incident_id":"b6b90c17","reason":"D084 active","identity":{"session_id":"e18eb85-current"}}\n')
        tx = self._software_recovery_executor()
        def mutate_after_snapshot(point):
            if point == 'after-recovery-state-snapshot':
                (self.root / 'state' / 'session_recovery_quarantine.json').write_text(
                    '{"owner":"runtime.charge.recovery_quarantine_journal","schema_version":1,"quarantined":true,"incident_id":"b6b90c17","reason":"changed","identity":{"session_id":"e18eb85-current"}}\n')
                raise RuntimeError('simulated interruption after snapshot')
        tx.failpoint = mutate_after_snapshot
        with self.assertRaisesRegex(RuntimeError, 'after snapshot'):
            tx.recover()
        self.assertFalse(self.service.running)
        self.assertEqual(0, self.service.starts)
        tx.failpoint = lambda _: None
        with self.assertRaisesRegex(TX.TransactionError, 'state differs from its durable stopped snapshot'):
            tx.recover()
        self.assertFalse(self.service.running)
        self.assertEqual(0, self.service.starts)
        self.assertIn('recovery_state_inventory', json.loads(tx.journal.read_text()))

    def test_started_reconciliation_commits_without_service_lifecycle_change(self):
        before = self._started_journal()
        result = self.tx.reconcile_started()
        self.assertEqual('COMMITTED', result['phase'])
        self.assertTrue(result['reconciled_without_restart'])
        self.assertEqual(release.SOURCE_SHA, (self.root / TX.MARKER).read_text().strip())
        self.assertEqual((0, 0), (self.service.stops, self.service.starts))
        self.assertTrue(self.service.running)
        self.assertEqual(before['transaction'], json.loads(self.tx.journal.read_text())['transaction'])

    def test_legacy_started_without_candidate_inventory_is_read_only_fail_closed(self):
        record = self._started_journal()
        record.pop('candidate_inventory')
        TX._atomic_json(self.tx.journal, record)
        journal_before = self.tx.journal.read_bytes()
        marker_before = (self.root / TX.MARKER).read_bytes()
        proof_calls = self.proof_counter

        with self.assertRaisesRegex(TX.TransactionError, 'legacy STARTED journal lacks candidate_inventory'):
            self.tx.reconcile_started()

        self.assertEqual(journal_before, self.tx.journal.read_bytes())
        self.assertEqual(marker_before, (self.root / TX.MARKER).read_bytes())
        self.assertEqual(proof_calls, self.proof_counter)
        self.assertEqual((0, 0), (self.service.stops, self.service.starts))
        self.assertTrue(self.service.running)

    def test_started_reconciliation_refusals_preserve_service_and_journal(self):
        mutations = ('env', 'unit', 'marker', 'backup')
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.tearDown(); self.setUp()
                self._started_journal()
                journal_before = self.tx.journal.read_bytes()
                if mutation == 'env': (self.root / '.env').write_text('TOKEN=changed\n')
                elif mutation == 'unit': (self.root / 'service.unit').write_text('changed')
                elif mutation == 'marker': (self.root / TX.MARKER).write_text(release.SOURCE_SHA + '\n')
                else: (self.root / 'backups' / json.loads(journal_before)['backup'] / 'app' / 'version').write_text('tampered')
                with self.assertRaises(TX.TransactionError): self.tx.reconcile_started()
                self.assertEqual(journal_before, self.tx.journal.read_bytes())
                self.assertEqual((0, 0), (self.service.stops, self.service.starts))
                self.assertTrue(self.service.running)

    def test_started_reconciliation_failure_before_marker_is_read_only(self):
        self._started_journal()
        journal_before = self.tx.journal.read_bytes()
        self.tx.failpoint = lambda point: (_ for _ in ()).throw(RuntimeError('injected')) if point == 'before-reconcile-marker' else None
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            self.tx.reconcile_started()
        self.assertEqual(journal_before, self.tx.journal.read_bytes())
        self.assertEqual(release.OLD_SHA, (self.root / TX.MARKER).read_text().strip())
        self.assertEqual((0, 0), (self.service.stops, self.service.starts))

    def test_healthy_transaction_commits_exact_sha_and_preserves_runtime_inputs(self):
        state_before = (self.root / 'state' / 'battery.db').read_bytes()
        env_before = (self.root / '.env').read_bytes()
        unit_before = (self.root / 'service.unit').read_bytes()
        record = self._run()
        self.assertEqual('COMMITTED', record['phase'])
        self.assertEqual(release.SOURCE_SHA, (self.root / '.deploy_sha').read_text().strip())
        self.assertEqual('new-app', (self.root / 'app' / 'version').read_text())
        self.assertEqual(state_before, (self.root / 'state' / 'battery.db').read_bytes())
        self.assertEqual(env_before, (self.root / '.env').read_bytes())
        self.assertEqual(unit_before, (self.root / 'service.unit').read_bytes())
        self.assertEqual('isolated-candidate-interpreter', (self.root / 'venv' / 'python').read_text())
        backup = self.root / 'backups' / ('d090-' + record['transaction'])
        self.assertEqual(TX.inventory(backup), record['backup_inventory'])
        self.assertNotIn('do-not-print-this-secret', json.dumps(record))
        self.assertEqual(1, self.service.starts)

    def test_small_analog_jitter_does_not_forge_or_break_fresh_off_proof(self):
        original_proof = self.tx.proof
        from dataclasses import replace
        def noisy_off():
            receipt = original_proof()
            jitter = 0.004 if self.proof_counter % 2 else 0.009
            return replace(receipt, ha102_voltage_v=jitter,
                           esp128_current_a=-jitter)
        self.tx.proof = noisy_off
        result = self._run()
        self.assertEqual("COMMITTED", result["phase"])
        self.assertEqual(release.SOURCE_SHA, (self.root / ".deploy_sha").read_text().strip())

    def test_faults_at_journal_and_swap_boundaries_recover_idempotently(self):
        points = (
            'after-journal-stopped', 'after-journal-backup_durable', 'before-swap',
            'after-old-app-rename-before-journal', 'after-journal-old_app_renamed',
            'after-old-app-rename', 'after-new-app-rename-before-journal',
            'after-journal-new_app_renamed', 'after-new-app-rename',
            'after-old-venv-rename-before-journal', 'after-journal-old_venv_renamed',
            'after-new-venv-rename-before-journal', 'after-journal-new_venv_renamed',
            'after-journal-started', 'post-start',
        )
        for point in points:
            with self.subTest(point=point):
                self.tearDown()
                self.setUp()
                with self.assertRaisesRegex(RuntimeError, 'injected fault'):
                    self._run(failpoint=point)
                self.assertEqual('ROLLED_BACK', json.loads(self.tx.journal.read_text())['phase'])
                self.assertEqual(release.OLD_SHA, (self.root / '.deploy_sha').read_text().strip())
                self.assertEqual('old-app', (self.root / 'app' / 'version').read_text())
                self.assertEqual('old-venv', (self.root / 'venv' / 'runtime').read_text())
                self.assertTrue(self.service.running)
                self.assertEqual('ROLLED_BACK', self.tx.recover()['phase'])

    def test_crash_after_initial_journal_recovers_only_verified_unchanged_preimage(self):
        with self.assertRaisesRegex(RuntimeError, 'injected fault'):
            self._run(failpoint='after-journal-before-stop')
        self.assertTrue(self.service.running)
        self.assertEqual('old-app', (self.root / 'app' / 'version').read_text())
        self.assertEqual('ROLLED_BACK', json.loads(self.tx.journal.read_text())['phase'])

    def test_post_stop_prebackup_preimage_tamper_never_restarts_old_service(self):
        def break_preimage_at_stopped(point):
            if point == 'after-journal-stopped':
                (self.root / 'app' / 'version').write_text('unexpected-local-mutation')
                raise RuntimeError('injected prebackup mutation')
        self.tx.failpoint = break_preimage_at_stopped
        with self.assertRaisesRegex(TX.TransactionError, 'baseline changed'):
            self._run()
        self.assertFalse(self.service.running)
        self.assertEqual(0, self.service.starts)
        record = json.loads(self.tx.journal.read_text())
        self.assertEqual('STOPPED', record['phase'])
        with self.assertRaisesRegex(TX.TransactionError, 'baseline changed'):
            self.tx.recover()
        self.assertFalse(self.service.running)

    def test_post_stop_prebackup_stale_proof_never_restarts_old_service(self):
        original = self.tx.proof
        def stale_only_when_stopped():
            value = original()
            if not self.service.running:
                return replace(value, captured_at_epoch=time.time() - 45)
            return value
        self.tx.proof = stale_only_when_stopped
        with self.assertRaisesRegex(release.GateError, 'expired'):
            self._run()
        self.assertFalse(self.service.running)
        self.assertEqual(0, self.service.starts)
        self.assertEqual('STOPPED', json.loads(self.tx.journal.read_text())['phase'])
        with self.assertRaisesRegex(release.GateError, 'expired'):
            self.tx.recover()
        self.assertFalse(self.service.running)

    def test_d134_started_live_state_drift_rejected_without_stop(self):
        self._started_journal()
        original_journal = self.tx.journal.read_bytes()
        (self.root / 'state' / 'battery.db').write_bytes(b'new-retired-session-state')
        stops_before = self.service.stops
        with self.assertRaisesRegex(TX.TransactionError, 'live preimage drift'):
            self.tx.recover()
        self.assertTrue(self.service.running)
        self.assertEqual(self.service.stops, stops_before)
        self.assertEqual(self.tx.journal.read_bytes(), original_journal)

    def test_d134_started_corrupt_backup_rejected_without_stop(self):
        record = self._started_journal()
        backup_app = self.root / 'backups' / record['backup'] / 'app' / 'version'
        backup_app.write_text('corrupt-backup')
        original_journal = self.tx.journal.read_bytes()
        with self.assertRaisesRegex(TX.TransactionError, 'backup inventory mismatch'):
            self.tx.recover()
        self.assertTrue(self.service.running)
        self.assertEqual(self.service.stops, 0)
        self.assertEqual(self.tx.journal.read_bytes(), original_journal)

    def test_d134_started_missing_baseline_rejected_without_stop(self):
        self._started_journal()
        record = json.loads(self.tx.journal.read_text())
        record.pop('baseline')
        self.tx.journal.write_text(json.dumps(record))
        original_journal = self.tx.journal.read_bytes()
        with self.assertRaisesRegex(TX.TransactionError, 'journal incomplete'):
            self.tx.recover()
        self.assertTrue(self.service.running)
        self.assertEqual(self.service.stops, 0)
        self.assertEqual(self.tx.journal.read_bytes(), original_journal)

    def test_backup_corruption_blocks_recovery_and_preserves_running_service(self):
        with self.assertRaisesRegex(RuntimeError, 'injected fault'):
            self._run(failpoint='before-swap')
        record = json.loads(self.tx.journal.read_text())
        backup_app = self.root / 'backups' / record['backup'] / 'app' / 'version'
        backup_app.write_text('tampered')
        record['phase'] = 'NEW_APP_RENAMED'  # model a process crash before automatic recovery
        self.tx.journal.write_text(json.dumps(record))
        with self.assertRaisesRegex(TX.TransactionError, 'backup (missing/corrupt|inventory mismatch)'):
            self.tx.recover()
        self.assertTrue(self.service.running)

    def test_bad_source_or_host_fails_before_service_mutation(self):
        with patch.object(release, 'verify_staged_release', return_value={'source_sha': '0' * 40}):
            with self.assertRaisesRegex(TX.TransactionError, 'pinned D090 source'):
                self.tx.prepare(self.staged, acceptance_record={}, evidence_dir=self.root)
        self.assertEqual(0, self.service.stops)
        bad_host = TX.D090Transaction(self.root, service=self.service, proof=self.proof,
            host_check=lambda: (_ for _ in ()).throw(TX.TransactionError('wrong host')),
            acceptance=lambda: None, venv_builder=self.build_venv, space_check=lambda _: None,
            candidate_validate=lambda *_: None, offline=True)
        with self.assertRaisesRegex(TX.TransactionError, 'wrong host'):
            bad_host.prepare(self.staged, acceptance_record={}, evidence_dir=self.root)
        self.assertEqual(0, self.service.stops)

    def test_preimage_requires_exact_reviewed_tree_inventory_pin(self):
        observed = hashlib.sha256(json.dumps(TX.inventory(self.root / 'app'),
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(observed, TX.verify_pinned_preimage_app(self.root / 'app', observed))
        with self.assertRaisesRegex(TX.TransactionError, 'not been captured'):
            TX.verify_pinned_preimage_app(self.root / 'app', None)
        with self.assertRaisesRegex(TX.TransactionError, 'differ from'):
            TX.verify_pinned_preimage_app(self.root / 'app', '0' * 64)

    def test_activation_rechecks_immutable_sha_and_prepared_candidate(self):
        with patch.object(release, 'verify_staged_release', return_value={'source_sha': release.SOURCE_SHA}), \
             patch.object(release, 'validate_physical_acceptance', return_value=None):
            prepared = self.tx.prepare(self.staged, acceptance_record={}, evidence_dir=self.root)
            forged = dict(prepared, source_sha='0' * 40)
            with self.assertRaisesRegex(TX.TransactionError, 'immutable D090 pins'):
                self.tx.activate(self.staged, acceptance_record={}, evidence_dir=self.root, prepared=forged)
            (Path(prepared['candidate']) / 'app' / 'version').write_text('tampered')
            with self.assertRaisesRegex(TX.TransactionError, 'prepared candidate changed'):
                self.tx.activate(self.staged, acceptance_record={}, evidence_dir=self.root, prepared=prepared)
        self.assertEqual(0, self.service.stops)

    def test_stale_off_proof_and_unaccepted_firmware_stop_before_systemd(self):
        stale = replace(self.proof(), captured_at_epoch=time.time() - 31)
        self.tx.proof = lambda: stale
        with patch.object(release, 'verify_staged_release', return_value={'source_sha': release.SOURCE_SHA}), \
             patch.object(release, 'validate_physical_acceptance', side_effect=release.GateError('firmware OPEN')):
            with self.assertRaisesRegex(release.GateError, 'firmware OPEN'):
                self.tx.prepare(self.staged, acceptance_record={}, evidence_dir=self.root)
        self.assertEqual(0, self.service.stops)
        self.tx.proof = lambda: stale
        with patch.object(release, 'verify_staged_release', return_value={'source_sha': release.SOURCE_SHA}), \
             patch.object(release, 'validate_physical_acceptance', return_value=None):
            with self.assertRaisesRegex(release.GateError, 'expired'):
                self.tx.prepare(self.staged, acceptance_record={}, evidence_dir=self.root)
        self.assertEqual(0, self.service.stops)


if __name__ == '__main__':
    unittest.main()
