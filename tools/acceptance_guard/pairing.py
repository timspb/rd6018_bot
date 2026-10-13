"""Build the guarded D061 dependency graph; never starts a service on import.

The operator-run harness calls run_prepared only after the physical bench and
exclusive-poller handover gates in REVIEW.md. It delegates lifecycle to the
exact canonical bot.py composition. No import replacement or method patching.
"""
import asyncio
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import stat

from .guard import Guard

SHA = '594a386e2b9fdd6bde9ebb15a5dfab30155291d6'
MANIFEST_SHA256 = '8e31b6d11c1fa2c9acbf038cd79e4f0adee7c011f8026656987c8891651ca288'
OVERRIDE_PATHS = frozenset()  # Core fixes are already present in 594a386.
SUPPLEMENTAL_PATHS = {
    'tools/acceptance_guard/__init__.py', 'tools/acceptance_guard/guard.py',
    'tools/acceptance_guard/adapters.py', 'tools/acceptance_guard/transient.py',
    'tools/acceptance_guard/pairing.py', 'tools/acceptance_guard/takeover.py',
}
# The Windows runner pins each overlay member and supplies the whole archive
# digest out of band over SSH; that digest authenticates this manifest too.
OVERRIDE_SHA256 = {}


from contextlib import contextmanager
import errno
import os

# Stable node-level inode shared by transient and takeover. Never unlink it:
# unlink/re-create permits simultaneous holders of different inodes.
NODE104_ACCEPTANCE_LOCK = Path('/run/lock/rd6018-d061-physical-acceptance.lock')


def _noncooperating_acceptance_pids(proc_root=Path('/proc')):
    """Find old per-stage Python owners which predate the shared flock."""
    existing = []
    for entry in Path(proc_root).iterdir():
        if not entry.name.isdecimal() or int(entry.name) == os.getpid():
            continue
        try:
            comm = (entry / 'comm').read_text().strip().lower()
            argv = (entry / 'cmdline').read_bytes().decode(errors='replace').replace('\\0', ' ')
        except FileNotFoundError:
            continue
        except PermissionError as exc:
            raise RuntimeError('cannot prove sole acceptance owner from /proc') from exc
        if not comm.startswith(('python', 'pypy')):
            continue
        if (('run_node104' in argv and 'rd6018-d061-takeover-' in argv)
                or 'tools.acceptance_guard.transient' in argv
                or '/acceptance_guard/transient.py' in argv):
            existing.append(int(entry.name))
    return sorted(existing)


@contextmanager
def node104_acceptance_gate():
    """Fail closed before production handover; retain through rollback/restore."""
    if os.geteuid() != 0:
        raise RuntimeError('global D061 acceptance gate requires node104 root')
    flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(NODE104_ACCEPTANCE_LOCK, flags, 0o600)
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != 0):
            raise RuntimeError('untrusted global D061 lock owner, type or permissions')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EACCES):
                raise RuntimeError('another node104 acceptance executor owns the global gate') from exc
            raise
        owners = _noncooperating_acceptance_pids()
        if owners:
            raise RuntimeError('legacy acceptance executor(s) still active: ' + ','.join(map(str, owners)))
        os.ftruncate(fd, 0)
        os.write(fd, ('pid=' + str(os.getpid()) + '\\n').encode('ascii'))
        os.fsync(fd)
        yield
    finally:
        os.close(fd)


def _safe_tree_files(root):
    root = Path(root)
    found = set()
    for path in root.rglob('*'):
        if path.is_symlink():
            raise RuntimeError('symlink in staged source: ' + str(path.relative_to(root)))
        if path.is_file():
            name = path.relative_to(root).as_posix()
            if name.startswith('.canonical-source/'):
                continue
            if name not in {'source-manifest.json', 'overlay-attestation.json'} and not name.startswith('state/'):
                found.add(name)
    return found


def verify_pairing(canonical, active, manifest, attestation):
    """Verify the independently retained canonical tree and exact accepted overlay."""
    canonical, active = Path(canonical), Path(active)
    verify_source(canonical, manifest)
    expected = json.loads(Path(manifest).read_text())
    att = json.loads(Path(attestation).read_text())
    overrides, supplemental = att.get('overrides'), att.get('supplemental')
    modes = att.get('modes')
    if (overrides != OVERRIDE_SHA256
            or set(supplemental or {}) != SUPPLEMENTAL_PATHS
            or set(modes or {}) != OVERRIDE_PATHS | SUPPLEMENTAL_PATHS):
        raise RuntimeError('overlay attestation path set mismatch')
    canonical_files = _safe_tree_files(canonical)
    active_files = _safe_tree_files(active)
    if canonical_files != set(expected):
        raise RuntimeError('canonical tree has missing or extra files')
    allowed = set(expected) | SUPPLEMENTAL_PATHS
    if active_files != allowed:
        raise RuntimeError('active tree has missing or unexpected files')
    for name, digest in expected.items():
        got = hashlib.sha256((active / name).read_bytes()).hexdigest()
        want = overrides[name] if name in OVERRIDE_PATHS else digest
        if got != want:
            raise RuntimeError('active staged file hash mismatch: ' + name)
        if name not in OVERRIDE_PATHS and stat.S_IMODE((active / name).stat().st_mode) != stat.S_IMODE((canonical / name).stat().st_mode):
            raise RuntimeError('canonical staged file mode mismatch: ' + name)
    for name, digest in supplemental.items():
        if hashlib.sha256((active / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('supplemental staged file hash mismatch: ' + name)
    for name, mode in modes.items():
        if stat.S_IMODE((active / name).stat().st_mode) != mode:
            raise RuntimeError('overlay staged file mode mismatch: ' + name)
    for name in SUPPLEMENTAL_PATHS:
        if stat.S_IMODE((active / name).stat().st_mode) & 0o111:
            raise RuntimeError('unexpected executable acceptance Python: ' + name)
    return len(expected)


def verify_source(source, manifest):
    raw = Path(manifest).read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise RuntimeError('untrusted exact-source manifest')
    expected = json.loads(raw)
    failures = [name for name, digest in expected.items()
        if hashlib.sha256((Path(source) / name).read_bytes()).hexdigest() != digest]
    if failures or len(expected) != 875:
        raise RuntimeError('exact canonical pairing source mismatch')
    return len(expected)


def bind_client(runtime, config, *, base_url, token):
    from .adapters import GuardedESPConnector, GuardedHAConnector, GuardedHassClient
    if runtime.hass.is_bound:
        raise RuntimeError('refusing to replace an initialized canonical client')
    # Conservative exact Leoch Ca/Ca ordinary-recipe ceiling. This adapter never
    # grants chemistry/Manual/HV authority, and safe_enable_output stays canonical.
    guard = Guard(voltage_ceiling=14.7)
    connectors = {'esp_direct': GuardedESPConnector, 'ha_esp': GuardedHAConnector}
    connector = connectors[config.default_connector](config, guard)
    client = GuardedHassClient(base_url, token, guard=guard, backend=connector)
    runtime.hass.bind(client)
    return guard, client


def assemble(source, manifest, *, canonical=None, attestation=None):
    if hashlib.sha256(Path(manifest).read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise RuntimeError('untrusted exact-source manifest')
    if canonical is None or attestation is None:
        raise RuntimeError('separate canonical source and overlay attestation required')
    verify_pairing(canonical, source, manifest, attestation)
    # Refuse a process that imported a different checkout before assembly.
    # Checking bot.py alone cannot prove its substrate or connector identity.
    import sys
    expected = json.loads(Path(manifest).read_text())
    source = Path(source).resolve()
    for name in expected:
        if not name.endswith('.py'):
            continue
        module_name = name[:-3].replace('/', '.')
        if module_name.endswith('.__init__'):
            module_name = module_name[:-9]
        module = sys.modules.get(module_name)
        if module is not None and Path(module.__file__).resolve() != source / name:
            raise RuntimeError('canonical module from wrong checkout: ' + module_name)
    if Path(sys.path[0]).resolve() != source:
        raise RuntimeError('exact source must be first on import path')
    from .adapters import GuardedD061Control, GuardedRuntimeSafety, AcceptanceUpdatesOnly
    from runtime import production_runtime as runtime
    from runtime.config import load_config
    from config import HA_URL, HA_TOKEN
    guard, client = bind_client(runtime, load_config(Path(source) / 'config'),
        base_url=HA_URL, token=HA_TOKEN)
    safety = GuardedRuntimeSafety(runtime)
    safety.acceptance_guard = guard
    safety.install()
    runtime.runtime_safety_guard = safety
    # Import AFTER binding: all canonical wrappers capture guarded dependencies.
    import bot
    if Path(bot.__file__).resolve() != (Path(source) / 'bot.py').resolve():
        raise RuntimeError('wrong bot.py imported')
    runtime.dp.update.outer_middleware(AcceptanceUpdatesOnly())
    control = GuardedD061Control(runtime)
    control.acceptance_guard = guard
    return bot._composition, control, client


async def run_prepared(source, manifest, *, physical_ready, sole_poller_ready,
                       canonical=None, attestation=None):
    # Callers supply independently reviewed current gates, never infer them from
    # unit results or telemetry. Missing readiness prevents even lifecycle startup.
    if physical_ready is not True or sole_poller_ready is not True:
        raise RuntimeError('physical supervision/bench and exclusive-poller gates required')
    # Read the real handover state; a caller's boolean cannot stop a second poller.
    service = subprocess.check_output(['systemctl', 'show', 'rd6018-bot.service',
        '-p', 'ActiveState', '-p', 'MainPID'], text=True)
    fields = dict(line.split('=', 1) for line in service.splitlines() if '=' in line)
    if fields.get('ActiveState') != 'inactive' or fields.get('MainPID') != '0':
        raise RuntimeError('production must be stopped before acceptance lifecycle')
    for process in Path('/proc').iterdir():
        if process.name.isdigit():
            try:
                args = (process / 'cmdline').read_bytes().decode(errors='replace').split('\0')
            except FileNotFoundError:
                continue
            if any(arg == 'bot.py' or arg.endswith('/bot.py') for arg in args):
                raise RuntimeError('another bot.py process is present')
    if Path.cwd().resolve() != (Path(source).resolve().parent / 'state'):
        raise RuntimeError('isolated acceptance state working directory required')
    # The acceptance launch uses -c to call this library, so /proc bot.py
    # checks alone cannot detect another such launch. Keep one OS lock for
    # the complete unchanged canonical lifecycle.
    with (Path.cwd() / '.acceptance-poller.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('another acceptance lifecycle holds the poller lock') from exc
        composition, control, _client = assemble(source, manifest,
            canonical=canonical, attestation=attestation)
        await composition.run(physical_test_control=control)
