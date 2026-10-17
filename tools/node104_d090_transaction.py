#!/usr/bin/env python3
"""D090 node-local release transaction owner.

The production CLI is deliberately fail-closed while firmware digest and
physical D061-D065 acceptance remain open. Transaction methods are injectable
so filesystem ordering and recovery can be exercised against an offline root.
No actuator, lease, HA, ESPHome, SSH, or service-manager mutation is issued by
this module except the explicitly owned systemd stop/start operations.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from typing import NamedTuple

import node104_d102_bench_admission as d102
import fcntl
from typing import Callable, Protocol

import node104_d090_release as release

UNIT = Path('/etc/systemd/system') / release.SERVICE
JOURNAL = 'D090_TRANSACTION.json'
MARKER = '.deploy_sha'
PHASES = ('PREPARED', 'STOPPED', 'BACKUP_DURABLE', 'CANDIDATE_READY',
          'OLD_APP_RENAMED', 'NEW_APP_RENAMED', 'OLD_VENV_RENAMED',
          'NEW_VENV_RENAMED', 'STARTED', 'COMMITTED', 'ROLLED_BACK')
# Must be set from the separately captured and reviewed exact installed app
# inventory. The old source tree is absent locally, so D090 leaves this OPEN.
PREIMAGE_APP_INVENTORY_SHA256: str | None = 'ef24cf5a66abe0991e4e5ceb04988c25806ee9a74d9025ebde00bf3161919171'
READ_ONLY_PROOF_COLLECTOR_SHA256: str | None = 'c6bf8f456c06da75816976946a9129ccd7619237b6e482874c25a4aa9951ace8'

# Reviewed D103 *test candidate*, never a D090 production release pin.
# The D104 trial has no production CLI entry point until a separately reviewed
# live trial observer / temporary socket lifecycle can be bound to this owner.
TRIAL_SOURCE_SHA = "b3cd0174a2918dbbc2ee3f9c908fa14d15089a29"
TRIAL_PIN = d102.SourcePin(
    TRIAL_SOURCE_SHA,
    "410af38f6a8ec059560aa1bc351b00a572a96121c3d93a216cbe86a433e84ae4",
    "f9c5725638b77a6e76e52cb7269b2e95f1fdbeda8b442d6c6b9811e347947575",
)
TRIAL_PURPOSE = "D104_OFF_ONLY_BENCH_TRIAL"
TRIAL_SCHEMA = 2
TRIAL_PHASES = ("PREPARED", "STOPPED", "BACKUP_DURABLE",
                "OLD_APP_RENAMED", "NEW_APP_RENAMED", "OLD_VENV_RENAMED",
                "NEW_VENV_RENAMED", "TRIAL_RUNNING", "TRIAL_STOPPED",
                "TRIAL_RESTORING", "TRIAL_RESTORED")
TRIAL_FINAL_PHASE = "TRIAL_RESTORED"


class TrialOffProof(NamedTuple):
    """Extra independent physical authority proof; never a device action.

    D090 PhysicalOffProof alone does not contain the autonomous mode,
    protection R16, lease remaining, or programmed limits. The trial requires
    these fields from a separately reviewed observer even when offline.
    """
    captured_at_epoch: float
    autonomous: bool
    lease_armed: bool
    lease_remaining_s: float
    lease_ttl_s: int
    protection_code: int
    modbus_age_s: float
    set_voltage_v: float
    set_current_a: float
    ovp_v: float
    ocp_a: float
    challenge: str

    def validate(self) -> None:
        import math
        numbers = (self.captured_at_epoch, self.lease_remaining_s,
                   self.modbus_age_s, self.set_voltage_v, self.set_current_a,
                   self.ovp_v, self.ocp_a)
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in numbers):
            raise TransactionError("trial proof has invalid numeric readings")
        if (type(self.autonomous) is not bool or type(self.lease_armed) is not bool
                or type(self.lease_ttl_s) is not int
                or type(self.protection_code) is not int
                or type(self.challenge) is not str or len(self.challenge) < 16):
            raise TransactionError("trial proof has invalid edge types/challenge")
        if not (0 <= time.time() - self.captured_at_epoch <= 30):
            raise TransactionError("trial edge proof stale or in the future")
        if (self.autonomous or self.lease_armed or self.lease_remaining_s != 0
                or self.lease_ttl_s != 900 or self.protection_code != 0
                or not 0 <= self.modbus_age_s <= 20
                or not 0 <= self.set_voltage_v <= 15.5
                or self.set_current_a < 0 or self.ovp_v < self.set_voltage_v
                or self.ocp_a < 0):
            raise TransactionError("trial edge state is not safe OFF/unmanaged")


class TransactionError(RuntimeError):
    pass


def _transaction_locked(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._locked():
            return method(self, *args, **kwargs)
    return wrapped


class Service(Protocol):
    def active(self) -> bool: ...
    def main_pid(self) -> int: ...
    def stop(self) -> None: ...
    def start(self) -> None: ...
    def stable(self, expected_sha: str) -> bool: ...
    def layout_valid(self) -> bool: ...


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inventory(root: Path) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    if not root.is_dir() or root.is_symlink():
        raise TransactionError(f'unsafe inventory root: {root}')
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[name] = {'link': os.readlink(path)}
        elif path.is_dir():
            result[name] = {'directory': True, 'mode': path.stat().st_mode & 0o777}
        elif path.is_file():
            result[name] = {'sha256': digest(path), 'size': path.stat().st_size,
                            'mode': path.stat().st_mode & 0o777}
        else:
            raise TransactionError(f'unsupported filesystem object: {name}')
    return result


def verify_pinned_preimage_app(app: Path, expected_sha256: str | None = PREIMAGE_APP_INVENTORY_SHA256) -> str:
    if expected_sha256 is None:
        raise TransactionError('installed pre-image app inventory has not been captured and pinned')
    observed = hashlib.sha256(json.dumps(inventory(app), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if observed != expected_sha256:
        raise TransactionError('installed app bytes differ from the accepted old-SHA pre-image inventory')
    return observed


def _sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _durable_tree(root: Path) -> None:
    for path in root.rglob('*'):
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
    for path in sorted((p for p in root.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        _sync_dir(path)
    _sync_dir(root)


def _atomic_json(path: Path, data: dict[str, object]) -> None:
    temp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    payload = (json.dumps(data, sort_keys=True, indent=2) + '\n').encode()
    with temp.open('xb') as stream:
        os.chmod(temp, 0o600)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    _sync_dir(path.parent)


def _atomic_text(path: Path, value: str) -> None:
    temp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    with temp.open('x', encoding='ascii') as stream:
        stream.write(value + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    _sync_dir(path.parent)


def _atomic_copy(source: Path, target: Path) -> None:
    temp = target.with_name(f'.{target.name}.{uuid.uuid4().hex}.tmp')
    shutil.copy2(source, temp)
    with temp.open('rb') as stream:
        os.fsync(stream.fileno())
    os.replace(temp, target)
    _sync_dir(target.parent)


class SystemdService:
    def _run(self, *args: str) -> str:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=60).strip()

    def active(self) -> bool:
        return self._run('systemctl', 'is-active', release.SERVICE) == 'active'

    def main_pid(self) -> int:
        return int(self._run('systemctl', 'show', release.SERVICE, '-p', 'MainPID', '--value'))

    def stop(self) -> None:
        self._run('systemctl', 'stop', release.SERVICE)

    def start(self) -> None:
        self._run('systemctl', 'start', release.SERVICE)

    def layout_valid(self) -> bool:
        value = self._run('systemctl', 'show', release.SERVICE, '-p', 'WorkingDirectory',
                          '-p', 'ProtectSystem', '-p', 'ExecStart', '-p', 'DropInPaths')
        required = ('WorkingDirectory=' + str(Path(release.ROOT) / 'state'),
                    'ProtectSystem=strict', str(Path(release.ROOT) / 'venv' / 'bin' / 'python'),
                    str(Path(release.ROOT) / 'app' / 'bot.py'), 'DropInPaths=')
        return all(item in value for item in required)

    def stable(self, expected_sha: str) -> bool:
        if expected_sha not in (release.SOURCE_SHA, release.OLD_SHA):
            return False
        if not self.active() or self.main_pid() <= 0:
            return False
        if self._run('systemctl', 'show', release.SERVICE, '-p', 'NRestarts', '--value') != '0':
            return False
        expected_script = str(Path(release.ROOT) / 'app' / 'bot.py').encode()
        processes = []
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                argv = proc.joinpath('cmdline').read_bytes().split(b'\0')
            except OSError:
                continue
            if expected_script in argv:
                processes.append(int(proc.name))
        if processes != [self.main_pid()]:
            return False
        logs = self._run('journalctl', '-u', release.SERVICE, '--since', '-30 seconds', '--no-pager', '-o', 'cat')
        if any(text in logs for text in ('Traceback (most recent call last)', 'Unauthorized', 'database is locked')):
            return False
        return any(text in logs for text in ('Start polling', 'Run polling for bot'))


class D090Transaction:
    """Single transaction owner with no default permission to activate."""
    def __init__(self, root: Path, *, service: Service, proof: Callable[[], release.PhysicalOffProof],
                 host_check: Callable[[], None], acceptance: Callable[[], None],
                 venv_builder: Callable[[Path, Path], None], failpoint: Callable[[str], None] | None = None,
                 space_check: Callable[[int], None] | None = None,
                 candidate_validate: Callable[[Path, Path], None] | None = None,
                 offline: bool = False,
                 trial_edge_proof: Callable[[], TrialOffProof] | None = None,
                 trial_socket_ready: Callable[[], bool] | None = None):
        self.root = root
        self.service = service
        self.proof = proof
        self.host_check = host_check
        self.acceptance = acceptance
        self.venv_builder = venv_builder
        self.failpoint = failpoint or (lambda _: None)
        self.space_check = space_check or self._space_check
        self.candidate_validate = candidate_validate or self._validate_candidate
        self.offline = offline
        self._lock_depth = 0
        self._proof_nonces: set[str] = set()
        self.trial_edge_proof = trial_edge_proof
        self.trial_socket_ready = trial_socket_ready
        self._trial_challenges: set[str] = set()

    def _read_proof(self, *, require_service_stopped: bool) -> release.PhysicalOffProof:
        proof = self.proof()
        release.validate_physical_off(proof, require_service_stopped=require_service_stopped)
        if any(nonce in self._proof_nonces for nonce in proof.source_nonces):
            raise TransactionError('physical proof challenge reused within transaction')
        self._proof_nonces.update(proof.source_nonces)
        return proof

    def _trial_read_proofs(self, reference: dict[str, object] | None = None,
                           *, service_stopped: bool) -> TrialOffProof:
        self._read_proof(require_service_stopped=service_stopped)
        if self.trial_edge_proof is None:
            raise TransactionError("trial independent edge observer not installed")
        value = self.trial_edge_proof()
        if not isinstance(value, TrialOffProof):
            raise TransactionError("trial observer returned unsupported proof type")
        value.validate()
        if value.challenge in self._trial_challenges:
            raise TransactionError("trial edge challenge replay")
        self._trial_challenges.add(value.challenge)
        if reference is not None:
            for field in ("set_voltage_v", "set_current_a", "ovp_v", "ocp_a"):
                expected = reference.get(field)
                if type(expected) not in (int, float) or abs(getattr(value, field) - expected) > .02:
                    raise TransactionError("trial programmed setpoints/protections changed")
        return value

    def _trial_gate(self) -> None:
        # The current release is an offline, fake-service transaction rehearsal.
        # Node104 trial execution is NOT wired to an actual actuator-capable CLI.
        if (not self.offline or self.root == Path(release.ROOT)
                or isinstance(self.service, SystemdService)):
            raise TransactionError("D104 production trial is not authorized by offline owner")
        if self.trial_edge_proof is None or self.trial_socket_ready is None:
            raise TransactionError("trial edge proof and socket readiness must be supplied")

    @contextmanager
    def _locked(self):
        if self._lock_depth:
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
            return
        lock_path = self.root / 'D090_TRANSACTION.lock'
        if lock_path.is_symlink():
            raise TransactionError('transaction lock path is a symlink')
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise TransactionError('another D090 transaction owns the lock') from exc
        self._lock_depth = 1
        try:
            yield
        finally:
            self._lock_depth = 0
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @property
    def journal(self) -> Path: return self.root / JOURNAL
    @property
    def backup_root(self) -> Path: return self.root / 'backups'

    def _space_check(self, amount: int) -> None:
        if shutil.disk_usage(self.root).free < amount * 2 + 256 * 1024 * 1024:
            raise TransactionError('insufficient free disk budget for durable backup and candidate')

    @staticmethod
    def _validate_candidate(python: Path, app: Path) -> None:
        with tempfile.TemporaryDirectory(prefix='d090-validation-', dir=app.parent) as temp:
            validation_app = Path(temp) / 'app'
            shutil.copytree(app, validation_app)
            env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': temp,
                   'TG_TOKEN': '123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi',
                   'HA_URL': 'http://127.0.0.1:8123', 'HA_LOCAL_URL': 'http://127.0.0.1:8123',
                   'HA_TOKEN': 'd090-offline-test-token', 'HA_PREFER_LOCAL': '0',
                   'ESPHOME_API_HOST': '127.0.0.1', 'ESPHOME_API_PORT': '6053',
                   'ESPHOME_API_KEY': 'd090-offline-test-key', 'ALLOWED_CHAT_IDS': '1',
                   'ALLOW_ALL_CHATS': '0', 'DEEPSEEK_BASE_URL': 'http://127.0.0.1:9'}
            subprocess.run([str(python), '-m', 'compileall', '-q', '.'], cwd=validation_app, env=env,
                           check=True, timeout=300)
            subprocess.run([str(python), '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'],
                           cwd=validation_app, env=env, check=True, timeout=1800)

    def _layout(self) -> None:
        if not self.offline and (self.root != Path(release.ROOT) or self.host_check is not production_host_check):
            raise TransactionError('production transaction requires the pinned root and node identity verifier')
        self.host_check()
        if self.root.is_symlink() or not self.root.is_dir():
            raise TransactionError('production root must be an ordinary directory')
        env_path, marker = self.root / '.env', self.root / MARKER
        if env_path.is_symlink() or not env_path.is_file() or marker.is_symlink() or not marker.is_file():
            raise TransactionError('environment and deployment marker must be ordinary files')
        if self.root == Path(release.ROOT):
            if self.root.resolve() != Path(release.ROOT):
                raise TransactionError('production root identity mismatch')
            if digest(self.root / '.env') != release.PINNED.service_environment_sha256:
                raise TransactionError('production service environment digest differs from pin')
            if self._unit_digest() != release.PINNED.systemd_unit_sha256:
                raise TransactionError('production systemd unit digest differs from pin')
            if not isinstance(self.service, SystemdService) or not self.service.layout_valid():
                raise TransactionError('systemd working directory/protection/ExecStart/drop-ins differ from pin')
            verify_pinned_preimage_app(self.root / 'app')
        for name in ('app', 'state', 'venv', 'backups'):
            path = self.root / name
            if not path.is_dir() or path.is_symlink() or path.stat().st_dev != self.root.stat().st_dev:
                raise TransactionError(f'ordinary same-filesystem layout required: {name}')
        if self.journal.exists() or self.journal.is_symlink():
            raise TransactionError('existing/incomplete D090 journal requires recovery')
        if marker.read_text(encoding='ascii').strip() != release.OLD_SHA:
            raise TransactionError('deployed marker does not match pinned pre-image SHA')

    def _phase(self, record: dict[str, object], phase: str) -> None:
        record['phase'] = phase
        record['updated_at_epoch'] = time.time()
        _atomic_json(self.journal, record)
        self.failpoint('after-journal-' + phase.lower())

    @_transaction_locked
    def prepare(self, staged_release: Path, *, acceptance_record: dict[str, object], evidence_dir: Path) -> dict[str, object]:
        """Read-only gates and independent candidate build, before service stop."""
        self._layout()
        manifest = release.verify_staged_release(staged_release)
        if manifest['source_sha'] != release.SOURCE_SHA:
            raise TransactionError('candidate source SHA is not the pinned D090 source')
        self.acceptance()
        release.validate_physical_acceptance(acceptance_record, evidence_dir)
        if not self.service.active() or self.service.main_pid() <= 0:
            raise TransactionError('expected active deployed service before preparation')
        self._read_proof(require_service_stopped=False)
        self._fresh_baseline()
        transaction = uuid.uuid4().hex
        candidate = self.root / ('candidate-' + transaction)
        candidate.mkdir(mode=0o700)
        shutil.copytree(staged_release / 'tree', candidate / 'app')
        self.venv_builder(candidate / 'venv', candidate / 'app')
        self.candidate_validate(candidate / 'venv' / 'bin' / 'python', candidate / 'app')
        _durable_tree(candidate)
        _sync_dir(self.root)
        self.space_check(sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file()))
        return {'transaction': transaction, 'candidate': str(candidate), 'source_sha': release.SOURCE_SHA,
                'manifest_sha256': release.PINNED.staging_manifest_sha256,
                'baseline': self._baseline(), 'candidate_inventory': inventory(candidate)}

    def _baseline(self) -> dict[str, object]:
        for name in ('.env', MARKER):
            path = self.root / name
            if path.is_symlink() or not path.is_file():
                raise TransactionError(f'{name} must remain an ordinary file')
        proof = self._read_proof(require_service_stopped=self.service.main_pid() == 0)
        # Physical analog readbacks are revalidated against bounded safety
        # limits on every fresh proof. Exact float equality across polls would
        # turn harmless ADC jitter into a spurious rollback; fingerprint the
        # stable ownership/containment invariants, not sampled analog values.
        observer = [proof.ha102_output_off, proof.esp128_output_off,
                    proof.native_sensor_state_fresh, proof.edge_lease_armed,
                    proof.edge_boot_quarantine, proof.physical_node_owner_count,
                    proof.active_session]
        return {'app': inventory(self.root / 'app'), 'state': inventory(self.root / 'state'),
                'venv': inventory(self.root / 'venv'), 'env': digest(self.root / '.env'),
                'unit': self._unit_digest(), 'marker': digest(self.root / MARKER),
                'observer': observer}

    def _fresh_baseline(self) -> None:
        self._baseline()

    def _unit_digest(self) -> str:
        # In tests the unit is mirrored below root; production reads the pinned unit.
        path = self.root / 'service.unit' if self.root.name.startswith('node104-fake') else UNIT
        if path.is_symlink() or not path.is_file():
            raise TransactionError('service unit unavailable or unsafe')
        return digest(path)

    @_transaction_locked
    def activate(self, staged_release: Path, *, acceptance_record: dict[str, object], evidence_dir: Path,
                 prepared: dict[str, object] | None = None) -> dict[str, object]:
        prepared = prepared or self.prepare(staged_release, acceptance_record=acceptance_record, evidence_dir=evidence_dir)
        self._layout()
        # Physical acceptance and a fresh independent pre-stop observation are
        # rechecked immediately before authorizing the service stop.
        manifest = release.verify_staged_release(staged_release)
        if manifest['source_sha'] != release.SOURCE_SHA:
            raise TransactionError('candidate source SHA is not the pinned D090 source')
        self.acceptance()
        release.validate_physical_acceptance(acceptance_record, evidence_dir)
        if not self.service.active() or self.service.main_pid() <= 0:
            raise TransactionError('service state changed after preparation')
        self._read_proof(require_service_stopped=False)
        self._assert_baseline(prepared['baseline'])
        candidate = Path(str(prepared['candidate']))
        transaction = prepared.get('transaction')
        if (prepared.get('source_sha') != release.SOURCE_SHA
                or prepared.get('manifest_sha256') != release.PINNED.staging_manifest_sha256
                or type(transaction) is not str or len(transaction) != 32
                or any(char not in '0123456789abcdef' for char in transaction)
                or candidate != self.root / ('candidate-' + transaction)):
            raise TransactionError('prepared transaction identity differs from immutable D090 pins')
        self._assert_candidate(candidate, prepared)
        source_tree = inventory(staged_release / 'tree')
        if inventory(candidate / 'app') != source_tree:
            raise TransactionError('prepared application bytes differ from the verified staged release')
        self.candidate_validate(candidate / 'venv' / 'bin' / 'python', candidate / 'app')
        backup = self.backup_root / ('d090-' + transaction)
        record: dict[str, object] = {'schema': 1, 'node': release.NODE, 'source_sha': release.SOURCE_SHA,
            'old_sha': release.OLD_SHA, 'transaction': transaction, 'phase': 'PREPARED',
            'candidate': candidate.name, 'backup': backup.name, 'baseline': prepared['baseline']}
        _atomic_json(self.journal, record)
        try:
            self.failpoint('after-journal-before-stop')
            self.service.stop()
            if self.service.main_pid() != 0:
                raise TransactionError('service MainPID did not reach zero')
            self._phase(record, 'STOPPED')
            self._read_proof(require_service_stopped=True)
            self._assert_baseline(prepared['baseline'])
            backup.mkdir(mode=0o700)
            for name in ('app', 'state', 'venv'):
                shutil.copytree(self.root / name, backup / name, symlinks=True)
            for name in ('.env', MARKER): shutil.copy2(self.root / name, backup / name)
            shutil.copy2(self._unit_path(), backup / 'service.unit')
            record['backup_inventory'] = inventory(backup)
            _durable_tree(backup)
            _sync_dir(self.backup_root)
            self._phase(record, 'BACKUP_DURABLE')
            self._assert_baseline(prepared['baseline'])
            self.failpoint('before-swap')
            (self.root / 'app').rename(self.root / ('old-app-' + transaction))
            _sync_dir(self.root)
            self.failpoint('after-old-app-rename-before-journal')
            self._phase(record, 'OLD_APP_RENAMED')
            self.failpoint('after-old-app-rename')
            (candidate / 'app').rename(self.root / 'app')
            _sync_dir(self.root)
            self.failpoint('after-new-app-rename-before-journal')
            self._phase(record, 'NEW_APP_RENAMED')
            self.failpoint('after-new-app-rename')
            (self.root / 'venv').rename(self.root / ('old-venv-' + transaction))
            _sync_dir(self.root)
            self.failpoint('after-old-venv-rename-before-journal')
            self._phase(record, 'OLD_VENV_RENAMED')
            (candidate / 'venv').rename(self.root / 'venv')
            _sync_dir(self.root)
            self.failpoint('after-new-venv-rename-before-journal')
            self._phase(record, 'NEW_VENV_RENAMED')
            self.service.start()
            self._phase(record, 'STARTED')
            if not self.service.stable(release.SOURCE_SHA):
                raise TransactionError('new service stability/one-process/OFF/lease proof missing')
            self._read_proof(require_service_stopped=False)
            self._assert_baseline(prepared['baseline'], allow_marker=True)
            self.failpoint('post-start')
            _atomic_text(self.root / MARKER, release.SOURCE_SHA)
            self._phase(record, 'COMMITTED')
            return record
        except BaseException:
            self.recover()
            raise

    def _unit_path(self) -> Path:
        return self.root / 'service.unit' if self.root.name.startswith('node104-fake') else UNIT

    def _assert_baseline(self, expected: object, *, allow_marker: bool = False) -> None:
        actual = self._baseline()
        if not isinstance(expected, dict): raise TransactionError('baseline evidence invalid')
        if allow_marker:
            for key in ('app', 'venv', 'marker'):
                actual[key] = expected[key]
        if actual != expected: raise TransactionError('state/environment/unit/observer baseline changed')

    def _assert_candidate(self, candidate: Path, prepared: dict[str, object]) -> None:
        try: candidate.resolve(strict=True).relative_to(self.root.resolve())
        except (OSError, ValueError) as exc: raise TransactionError('candidate escapes production root') from exc
        if candidate.is_symlink() or not candidate.is_dir() or candidate.stat().st_dev != self.root.stat().st_dev:
            raise TransactionError('candidate must be ordinary and same-filesystem')
        if inventory(candidate) != prepared.get('candidate_inventory'):
            raise TransactionError('prepared candidate changed')

    @_transaction_locked
    def begin_trial(self, staged_release: Path) -> dict[str, object]:
        """D104 OFF-only *offline* trial; never a permanent D090 commit.

        Only the existing D090 owner changes fake service/app/venv/state. No
        production CLI route is exposed and a live trial is deliberately gated.
        All trial transitions require independent physical + native edge proofs.
        """
        self._trial_gate()
        self._layout()
        d102.verify_source(staged_release, pin=TRIAL_PIN)
        if not self.service.active() or self.service.main_pid() <= 0:
            raise TransactionError("trial requires stable original service")
        if not self.service.stable(release.OLD_SHA):
            raise TransactionError("trial original service identity not stable")
        edge = self._trial_read_proofs(service_stopped=False)
        baseline = self._baseline()
        ident = uuid.uuid4().hex
        candidate = self.root / ("candidate-" + ident)
        candidate.mkdir(mode=0o700)
        try:
            shutil.copytree(staged_release / "tree", candidate / "app")
            self.venv_builder(candidate / "venv", candidate / "app")
            self.candidate_validate(candidate / "venv" / "bin" / "python", candidate / "app")
            if inventory(candidate / "app") != inventory(staged_release / "tree"):
                raise TransactionError("trial prepared candidate differs from reviewed source")
            _durable_tree(candidate)
            _sync_dir(self.root)
            self.space_check(sum(x.stat().st_size for x in self.root.rglob("*") if x.is_file()))
            self._trial_read_proofs(reference=edge._asdict(), service_stopped=False)
            self._assert_baseline(baseline)
        except BaseException:
            # Before journaling and stopping the service, the candidate is
            # disposable; service and production app are unchanged.
            if candidate.is_dir() and not candidate.is_symlink():
                shutil.rmtree(candidate)
            raise
        record: dict[str, object] = {
            "schema": TRIAL_SCHEMA, "purpose": TRIAL_PURPOSE, "node": release.NODE,
            "transaction": ident, "source_sha": TRIAL_SOURCE_SHA,
            "old_sha": release.OLD_SHA, "manifest_sha256": TRIAL_PIN.manifest_sha256,
            "archive_sha256": TRIAL_PIN.archive_sha256, "phase": "PREPARED",
            "candidate": candidate.name, "backup": "d104-" + ident,
            "baseline": baseline, "candidate_inventory": inventory(candidate),
            "edge_setpoints": {field: getattr(edge, field) for field in
                               ("set_voltage_v", "set_current_a", "ovp_v", "ocp_a")},
        }
        _atomic_json(self.journal, record)
        try:
            self.failpoint("trial-after-journal-prepared")
            self._trial_read_proofs(reference=record["edge_setpoints"], service_stopped=False)
            self._assert_baseline(baseline)
            self.service.stop()
            if self.service.main_pid() != 0:
                raise TransactionError("trial existing owner did not stop")
            self._phase(record, "STOPPED")
            self._trial_read_proofs(reference=record["edge_setpoints"], service_stopped=True)
            self._assert_baseline(baseline)
            backup = self.backup_root / record["backup"]
            backup.mkdir(mode=0o700)
            for name in ("app", "state", "venv"):
                shutil.copytree(self.root / name, backup / name, symlinks=True)
            for name in (".env", MARKER):
                shutil.copy2(self.root / name, backup / name)
            shutil.copy2(self._unit_path(), backup / "service.unit")
            record["backup_inventory"] = inventory(backup)
            _durable_tree(backup)
            _sync_dir(self.backup_root)
            self._phase(record, "BACKUP_DURABLE")
            self._assert_baseline(baseline)
            self.failpoint("trial-before-swap")
            for name in ("app", "venv"):
                old_name = "old-" + name + "-" + ident
                (self.root / name).rename(self.root / old_name)
                _sync_dir(self.root)
                self.failpoint("trial-after-old-" + name + "-rename-before-journal")
                self._phase(record, "OLD_" + name.upper() + "_RENAMED")
                (candidate / name).rename(self.root / name)
                _sync_dir(self.root)
                self.failpoint("trial-after-new-" + name + "-rename-before-journal")
                self._phase(record, "NEW_" + name.upper() + "_RENAMED")
            _atomic_text(self.root / MARKER, TRIAL_SOURCE_SHA)
            self.failpoint("trial-before-start")
            self.service.start()
            if not self.service.stable(TRIAL_SOURCE_SHA):
                raise TransactionError("trial candidate service did not become stable")
            # An enabled physical-test AF_UNIX endpoint belongs to the SAME
            # production composition; no second Telegram polling instance.
            if not self.trial_socket_ready():
                raise TransactionError("trial production coordinator socket not ready")
            self._trial_read_proofs(reference=record["edge_setpoints"], service_stopped=False)
            self._phase(record, "TRIAL_RUNNING")
            return record
        except BaseException:
            # Shared D090 owner restores the verified old preimage and does
            # not authorize a new release after a failed trial.
            self.recover()
            raise

    @_transaction_locked
    def finish_trial(self) -> dict[str, object]:
        """Restore exact old app/venv/state/environment after OFF-only trial."""
        self._trial_gate()
        return self.recover()

    def _recover_trial(self, record: dict[str, object]) -> dict[str, object]:
        """Only D090's locked recover() dispatch calls this schema-2 branch."""
        self._trial_gate()
        ident = record.get("transaction")
        if (record.get("purpose") != TRIAL_PURPOSE or record.get("node") != release.NODE
                or record.get("source_sha") != TRIAL_SOURCE_SHA
                or record.get("old_sha") != release.OLD_SHA
                or record.get("manifest_sha256") != TRIAL_PIN.manifest_sha256
                or record.get("archive_sha256") != TRIAL_PIN.archive_sha256
                or type(ident) is not str or len(ident) != 32
                or any(c not in "0123456789abcdef" for c in ident)
                or record.get("phase") not in TRIAL_PHASES
                or record.get("candidate") != "candidate-" + ident
                or record.get("backup") != "d104-" + ident):
            raise TransactionError("trial journal identity invalid; remain contained")
        baseline = record.get("baseline")
        edges = record.get("edge_setpoints")
        if type(baseline) is not dict or type(edges) is not dict or set(edges) != {
                "set_voltage_v", "set_current_a", "ovp_v", "ocp_a"}:
            raise TransactionError("trial preimage/edge identity missing")
        backup = self.backup_root / str(record["backup"])
        expected = record.get("backup_inventory")
        if record["phase"] == TRIAL_FINAL_PHASE:
            if record.get("rollback_without_backup") is True:
                if backup.exists() or backup.is_symlink():
                    raise TransactionError("terminal trial backup identity changed")
            elif (backup.is_symlink() or not backup.is_dir() or type(expected) is not dict
                  or inventory(backup) != expected):
                raise TransactionError("terminal trial backup missing/corrupt")
            self._assert_baseline(baseline)
            self._trial_read_proofs(reference=edges, service_stopped=False)
            if not self.service.active() or not self.service.stable(release.OLD_SHA):
                raise TransactionError("restored old service no longer stable")
            return record
        # If a complete backup has not been durably journaled, the app/venv
        # rename boundary must never have been crossed. Demand exact original
        # pre-image and fresh OFF proof before a restart.
        if record["phase"] in ("PREPARED", "STOPPED"):
            self._trial_read_proofs(reference=edges,
                                    service_stopped=self.service.main_pid() == 0)
            self._assert_baseline(baseline)
            if self.service.main_pid() == 0:
                self.service.start()
            if not self.service.active() or not self.service.stable(release.OLD_SHA):
                raise TransactionError("trial original preimage not stable")
            self._trial_read_proofs(reference=edges, service_stopped=False)
            record["rollback_without_backup"] = True
            self._phase(record, TRIAL_FINAL_PHASE)
            return record
        # All other phases require a completely recorded *durable* backup.
        if (backup.is_symlink() or not backup.is_dir()
                or type(expected) is not dict or inventory(backup) != expected):
            raise TransactionError("trial backup missing/corrupt; remain contained")
        for name in ("app", "state", "venv"):
            if inventory(backup / name) != baseline.get(name):
                raise TransactionError("trial saved preimage is corrupted")
        if (digest(backup / ".env") != baseline.get("env")
                or digest(backup / MARKER) != baseline.get("marker")
                or digest(backup / "service.unit") != baseline.get("unit")):
            raise TransactionError("trial saved configuration differs from preimage")
        if (digest(self.root / ".env") != baseline.get("env")
                or self._unit_digest() != baseline.get("unit")):
            raise TransactionError("trial live configuration changed")
        if self.root.joinpath(MARKER).is_symlink():
            raise TransactionError("trial marker symlink is unsafe")
        if digest(self.root / MARKER) not in (
                baseline["marker"], hashlib.sha256((TRIAL_SOURCE_SHA + "\n").encode()).hexdigest()):
            raise TransactionError("trial deployment marker is not an accepted value")
        # Never stop an autonomous or energized PSU in order to restore code.
        self._trial_read_proofs(reference=edges, service_stopped=self.service.main_pid() == 0)
        if self.service.main_pid() != 0:
            self.service.stop()
        if self.service.main_pid() != 0:
            raise TransactionError("trial process still active; cannot restore")
        self._phase(record, "TRIAL_STOPPED")
        self._trial_read_proofs(reference=edges, service_stopped=True)
        self._phase(record, "TRIAL_RESTORING")
        for name in ("app", "state", "venv"):
            target = self.root / name
            replacement = self.root / ("trial-restore-" + name + "-" + ident)
            failed = self.root / ("trial-displaced-" + name + "-" + ident)
            if replacement.is_symlink() or failed.is_symlink() or target.is_symlink():
                raise TransactionError("trial restore path is a symlink")
            if replacement.exists():
                shutil.rmtree(replacement)
            shutil.copytree(backup / name, replacement, symlinks=True)
            _durable_tree(replacement)
            if target.exists():
                if failed.exists():
                    shutil.rmtree(failed)
                os.replace(target, failed)
            os.replace(replacement, target)
            _sync_dir(self.root)
            self.failpoint("trial-restore-" + name)
        _atomic_copy(backup / ".env", self.root / ".env")
        _atomic_copy(backup / MARKER, self.root / MARKER)
        # Verify byte-level original app, venv and persistent state BEFORE
        # restarting old bot, plus independent fresh, unarmed, OFF proof.
        self._assert_baseline(baseline)
        self._trial_read_proofs(reference=edges, service_stopped=True)
        self.service.start()
        if not self.service.stable(release.OLD_SHA):
            raise TransactionError("restored old service unstable")
        self._trial_read_proofs(reference=edges, service_stopped=False)
        self._phase(record, TRIAL_FINAL_PHASE)
        return record

    @_transaction_locked
    def recover(self) -> dict[str, object]:
        if not self.offline and (self.root != Path(release.ROOT) or self.host_check is not production_host_check):
            raise TransactionError('production recovery requires the pinned root and node identity verifier')
        self.host_check()
        if self.root.is_symlink() or not self.root.is_dir() or self.backup_root.is_symlink() or not self.backup_root.is_dir():
            raise TransactionError('unsafe recovery root/layout; remain contained')
        if not self.journal.is_file() or self.journal.is_symlink():
            raise TransactionError('journal missing/corrupt; remain contained')
        try: record = json.loads(self.journal.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc: raise TransactionError('journal corrupt; remain contained') from exc
        if isinstance(record, dict) and record.get("schema") == TRIAL_SCHEMA:
            return self._recover_trial(record)
        if (type(record) is not dict or type(record.get('schema')) is not int or record.get('schema') != 1 or record.get('node') != release.NODE
                or record.get('source_sha') != release.SOURCE_SHA or record.get('old_sha') != release.OLD_SHA
                or type(record.get('transaction')) is not str or len(record['transaction']) != 32
                or any(char not in '0123456789abcdef' for char in record['transaction'])
                or record.get('phase') not in PHASES):
            raise TransactionError('journal identity invalid; remain contained')
        if record.get('backup') != 'd090-' + record['transaction']:
            raise TransactionError('journal backup identity invalid; remain contained')
        backup = self.backup_root / str(record.get('backup'))
        expected = record.get('backup_inventory')
        if (record['phase'] in ('PREPARED', 'STOPPED')
                and not backup.exists() and not backup.is_symlink()):
            # No backup means the transaction has not crossed any app/venv
            # rename boundary. A crash can occur after STOPPED was journaled
            # but before backup creation. Verify the complete pre-image and
            # fresh OFF proof before resuming the old service; otherwise remain
            # contained with the service stopped.
            baseline = record.get('baseline')
            if type(baseline) is not dict:
                raise TransactionError('pre-backup journal lacks baseline; remain contained')
            proof = self._read_proof(require_service_stopped=self.service.main_pid() == 0)
            self._assert_baseline(baseline)
            if self.service.main_pid() == 0:
                self.service.start()
            if not self.service.active() or not self.service.stable(release.OLD_SHA):
                raise TransactionError('pre-image service not positively stable; remain contained')
            self._read_proof(require_service_stopped=False)
            record['rollback_without_backup'] = True
            record['phase'] = 'ROLLED_BACK'
            _atomic_json(self.journal, record)
            return record
        if record['phase'] in ('COMMITTED', 'ROLLED_BACK'):
            if (record['phase'] == 'ROLLED_BACK'
                    and record.get('rollback_without_backup') is True
                    and not backup.exists() and not backup.is_symlink()):
                baseline = record.get('baseline')
                if type(baseline) is not dict:
                    raise TransactionError('pre-backup rollback lacks baseline; operator review required')
                self._assert_baseline(baseline)
                if not self.service.active() or not self.service.stable(release.OLD_SHA):
                    raise TransactionError('pre-image service is not stable after pre-backup rollback')
                self._read_proof(require_service_stopped=False)
                return record
            if not backup.is_dir() or backup.is_symlink() or type(expected) is not dict or inventory(backup) != expected:
                raise TransactionError('backup missing/corrupt; terminal transaction requires operator review')
            return record
        if self.service.main_pid() != 0:
            self.service.stop()
        if self.service.main_pid() != 0: raise TransactionError('process remains live; recovery contained')
        self._read_proof(require_service_stopped=True)
        if not backup.is_dir() or backup.is_symlink() or type(expected) is not dict or inventory(backup) != expected:
            raise TransactionError('backup missing/corrupt; service remains stopped')
        for name in ('.env', MARKER, 'service.unit'):
            path = backup / name
            if path.is_symlink() or not path.is_file():
                raise TransactionError(f'backup configuration is unsafe: {name}')
        if digest(backup / '.env') != record['baseline']['env'] or digest(backup / 'service.unit') != record['baseline']['unit']:
            raise TransactionError('backup configuration evidence mismatch; remain contained')
        if (inventory(backup / 'app') != record['baseline']['app']
                or inventory(backup / 'state') != record['baseline']['state']
                or inventory(backup / 'venv') != record['baseline']['venv']
                or digest(backup / MARKER) != record['baseline']['marker']):
            raise TransactionError('backup differs from pre-image inventory; remain contained')
        if ((self.root / '.env').is_symlink() or not (self.root / '.env').is_file()
                or (self.root / MARKER).is_symlink() or not (self.root / MARKER).is_file()):
            raise TransactionError('environment/marker path changed; service remains stopped')
        current_marker = digest(self.root / MARKER)
        candidate_marker = hashlib.sha256((release.SOURCE_SHA + '\n').encode()).hexdigest()
        if (digest(self.root / '.env') != record['baseline']['env']
                or self._unit_digest() != record['baseline']['unit']
                or inventory(self.root / 'state') != record['baseline']['state']
                or current_marker not in (record['baseline']['marker'], candidate_marker)):
            raise TransactionError('environment/unit/state/marker changed; service remains stopped')
        # Restore every inventoried component through sibling directories and
        # atomic renames; preserve state and venv exactly from the backup.
        for name in ('app', 'state', 'venv'):
            replacement = self.root / ('restore-' + name + '-' + str(record['transaction']))
            if replacement.exists(): shutil.rmtree(replacement)
            shutil.copytree(backup / name, replacement, symlinks=True)
            _durable_tree(replacement)
            target = self.root / name
            if target.exists(): os.replace(target, self.root / ('failed-' + name + '-' + str(record['transaction'])))
            os.replace(replacement, target)
            _sync_dir(self.root)
        _atomic_copy(backup / '.env', self.root / '.env')
        _atomic_copy(backup / MARKER, self.root / MARKER)
        if self._unit_digest() != digest(backup / 'service.unit'):
            raise TransactionError('service unit changed; remain contained')
        self._read_proof(require_service_stopped=True)
        self.service.start()
        self._read_proof(require_service_stopped=False)
        if not self.service.active() or self.service.main_pid() <= 0 or not self.service.stable(release.OLD_SHA):
            raise TransactionError('restored service not positively stable; inspect contained state')
        record['phase'] = 'ROLLED_BACK'
        _atomic_json(self.journal, record)
        return record


def production_host_check() -> None:
    if (os.geteuid() != 0 or socket.gethostname() != release.HOSTNAME
            or Path('/etc/machine-id').read_text(encoding='ascii').strip() != release.MACHINE_ID):
        raise TransactionError('requires root on the pinned node104 hostname and machine ID')


def production_venv_builder(path: Path, app: Path) -> None:
    python311 = shutil.which('python3.11')
    if not python311:
        raise TransactionError('pinned Python 3.11 interpreter unavailable for isolated candidate')
    subprocess.run([python311, '-m', 'venv', str(path)], check=True, timeout=120)
    python = path / 'bin/python'
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(app / 'requirements.txt')],
                   check=True, timeout=1800)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'activate', 'recover'))
    parser.add_argument('--release', type=Path)
    parser.add_argument('--acceptance', type=Path)
    parser.add_argument('--evidence-dir', type=Path)
    parser.add_argument('--proof-collector', type=Path)
    args = parser.parse_args(argv)
    production_host_check()
    if not args.proof_collector or READ_ONLY_PROOF_COLLECTOR_SHA256 is None:
        parser.error('pinned independent read-only proof collector is not configured; D090 remains BLOCKED')
    collector = args.proof_collector
    try:
        collector.resolve(strict=True).relative_to(Path(release.ROOT).resolve(strict=True))
    except (OSError, ValueError):
        parser.error('proof collector must be inside the pinned production root')
    if collector.is_symlink() or not collector.is_file() or digest(collector) != READ_ONLY_PROOF_COLLECTOR_SHA256:
        parser.error('proof collector differs from its reviewed SHA256 pin')
    if args.phase != 'recover':
        if not args.release or not args.acceptance or not args.evidence_dir:
            parser.error('--release, --acceptance and --evidence-dir are required')
        if release.PINNED.firmware_digest is None or release.PHYSICAL_SIGNER_KEY_SHA256 is None:
            parser.error('exact firmware digest and signed physical acceptance trust root are not configured; D090 remains BLOCKED')
    python = Path(release.ROOT) / 'venv' / 'bin' / 'python'

    def read_proof() -> release.PhysicalOffProof:
        raw = subprocess.check_output([str(python), str(collector)], text=True,
                                      stderr=subprocess.STDOUT, timeout=15)
        value = json.loads(raw)
        required = {field for field in release.PhysicalOffProof.__dataclass_fields__}
        if type(value) is not dict or set(value) != required:
            raise TransactionError('read-only collector returned an unknown proof schema')
        value['source_nonces'] = tuple(value['source_nonces']) if type(value['source_nonces']) is list else value['source_nonces']
        return release.PhysicalOffProof(**value)

    executor = D090Transaction(Path(release.ROOT), service=SystemdService(), proof=read_proof,
        host_check=production_host_check, acceptance=lambda: None,
        venv_builder=production_venv_builder)
    if args.phase == 'recover':
        result = executor.recover()
    else:
        try:
            acceptance_record = json.loads(args.acceptance.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise TransactionError(f'physical acceptance record invalid: {exc}') from exc
        if type(acceptance_record) is not dict:
            raise TransactionError('physical acceptance record must be an object')
        if args.phase == 'prepare':
            result = executor.prepare(args.release, acceptance_record=acceptance_record,
                                      evidence_dir=args.evidence_dir)
        else:
            result = executor.activate(args.release, acceptance_record=acceptance_record,
                                       evidence_dir=args.evidence_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
