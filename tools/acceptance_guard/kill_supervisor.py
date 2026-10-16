"""Opt-in, fail-closed D061 adopted-child kill acceptance supervisor.

This module has no production imports and performs no action at import time.
It is an engineering foundation; it is not physical authorization.
"""
from __future__ import annotations

import errno
import fcntl
import hashlib
import os
from pathlib import Path
import signal
import stat
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from .independent_off import independent_output_off


class Stage(str, Enum):
    PREARM = "PREARM"
    ADOPTED_CONFIRMED = "ADOPTED_CONFIRMED"
    KILLED = "KILLED"
    OFF_PROVED = "OFF_PROVED"
    LEASE_DISARMED = "LEASE_DISARMED"
    RESTORE_ALLOWED = "RESTORE_ALLOWED"
    FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class ChildIdentity:
    pid: int
    cmdline: tuple[str, ...]
    start_time: int
    cgroup: str
    stage_sha256: str


def _proc_identity(pid: int, proc_root: Path = Path("/proc")) -> tuple[tuple[str, ...], int, str]:
    root = Path(proc_root) / str(pid)
    raw = (root / "cmdline").read_bytes()
    args = tuple(x.decode(errors="strict") for x in raw.split(b"\0") if x)
    if not args:
        raise RuntimeError("child cmdline unavailable")
    stat_line = (root / "stat").read_text()
    # comm can contain spaces and parentheses; fields after the final ')' start at field 3.
    fields = stat_line[stat_line.rfind(")") + 2:].split()
    start = int(fields[19])  # Linux /proc/PID/stat field 22.
    cgroup = (root / "cgroup").read_text()
    return args, start, cgroup


def verify_child(identity: ChildIdentity, *, proc_root: Path = Path("/proc"),
                 stage_file: Path | None = None) -> None:
    if identity.pid <= 1 or identity.pid == os.getpid():
        raise RuntimeError("invalid acceptance child PID")
    args, start, cgroup = _proc_identity(identity.pid, proc_root)
    if any(Path(arg).name == "bot.py" or arg.endswith("/bot.py") for arg in args):
        raise RuntimeError("production bot is never an acceptance child")
    if (args != identity.cmdline or start != identity.start_time
            or cgroup != identity.cgroup):
        raise RuntimeError("acceptance child identity changed or PID was reused")
    if stage_file is None or hashlib.sha256(Path(stage_file).read_bytes()).hexdigest() != identity.stage_sha256:
        raise RuntimeError("acceptance child stage SHA mismatch")


class GlobalLock:
    """Lock one pre-created root-owned 0600 regular inode; never creates/unlinks it."""
    def __init__(self, path: Path, *, euid: Callable[[], int] = os.geteuid,
                 owner_uid: int = 0):
        self.path = Path(path)
        self.fd: int | None = None
        self.euid = euid
        self.owner_uid = owner_uid

    def acquire(self) -> None:
        if self.euid() != 0:
            raise RuntimeError("acceptance supervisor requires root")
        before = self.path.lstat()
        if stat.S_ISLNK(before.st_mode):
            raise RuntimeError("global acceptance lock must not be a symlink")
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != self.owner_uid
                or stat.S_IMODE(before.st_mode) != 0o600):
            raise RuntimeError("global acceptance lock must be root-owned regular 0600")
        fd = os.open(self.path, os.O_RDWR | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
        try:
            after = os.fstat(fd)
            if ((before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                    or not stat.S_ISREG(after.st_mode) or after.st_uid != self.owner_uid
                    or stat.S_IMODE(after.st_mode) != 0o600):
                raise RuntimeError("global acceptance lock inode changed or is untrusted")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in (errno.EAGAIN, errno.EACCES):
                    raise RuntimeError("global acceptance lock is occupied") from exc
                raise
            self.fd = fd
        except BaseException:
            os.close(fd)
            raise

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


ADOPTION_CHECKS = frozenset({
    'pb_managed', 'adoption_active', 'output_on_dual_source',
    'fingerprint_within_tolerance', 'guard_fresh', 'edge_lease_armed',
    'edge_lease_not_quarantined', 'edge_lease_not_tripped', 'lease_armed',
    'lease_not_tripped', 'lease_not_quarantined', 'lease_modbus_fresh',
    'lease_remaining_fresh', 'raw_protection_normal',
    'setpoint_readback_voltage_v', 'setpoint_readback_current_a',
    'setpoint_readback_ovp_v', 'setpoint_readback_ocp_a', 'safe_temperature',
})
assert len(ADOPTION_CHECKS) == 19


def adopted_proof_is_full(proof: Any) -> bool:
    checks = proof.get('checks') if isinstance(proof, dict) else None
    return (isinstance(checks, dict) and set(checks) == ADOPTION_CHECKS
            and all(value is True for value in checks.values())
            and proof.get('failed_predicates') == [])


class KillSupervisor:
    """Parent-owned bounded caretaker. Callbacks must be independent of child."""
    def __init__(self, *, lock: GlobalLock, child: ChildIdentity,
                 stage_file: Path, proof_provider: Callable[[], dict],
                 ha_off_command: Callable[[], Any], native_off_command: Callable[[], Any],
                 ha_readback: Callable[[], dict], native_readback: Callable[[], dict],
                 disarm_lease: Callable[[], Any], lease_readback: Callable[[], dict],
                 retire_ownership: Callable[[], Any], retire_poller: Callable[[], Any],
                 restore_production: Callable[[], Any], expected_generation: int,
                 kill: Callable[[int, int], Any] = os.kill,
                 clock: Callable[[], float] = time.time,
                 monotonic: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Any] = time.sleep,
                 max_lifecycle_s: float = 44.0):
        self.lock, self.child, self.stage_file = lock, child, Path(stage_file)
        self.proof_provider = proof_provider
        self.off_callbacks = dict(ha_off_command=ha_off_command, native_off_command=native_off_command,
            ha_readback=ha_readback, native_readback=native_readback,
            disarm_lease=disarm_lease, lease_readback=lease_readback,
            retire_ownership=retire_ownership, retire_poller=retire_poller)
        self.restore_production, self.expected_generation = restore_production, expected_generation
        self.kill, self.clock, self.monotonic, self.sleep = kill, clock, monotonic, sleep
        self.max_lifecycle_s = min(float(max_lifecycle_s), 44.0)
        if self.max_lifecycle_s <= 0:
            raise ValueError("bounded lifecycle timeout required")
        self.stage = Stage.PREARM
        self.result: str | None = None

    def run(self) -> str:
        started = self.monotonic()
        self.lock.acquire()
        try:
            verify_child(self.child, stage_file=self.stage_file)
            proof = self.proof_provider()
            if not adopted_proof_is_full(proof):
                raise RuntimeError("full 19/19 D061 adopted proof required before child kill")
            self.stage = Stage.ADOPTED_CONFIRMED
            verify_child(self.child, stage_file=self.stage_file)
            if self.monotonic() - started >= self.max_lifecycle_s:
                raise TimeoutError("acceptance lifecycle bound exceeded")
            self.kill(self.child.pid, signal.SIGKILL)
            self.stage = Stage.KILLED
            deadline = started + self.max_lifecycle_s
            self._wait_child_death(deadline)
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                raise TimeoutError("acceptance lifecycle bound exceeded")
            independent_output_off(**self.off_callbacks,
                expected_generation=self.expected_generation,
                timeout_s=min(8.0, remaining), clock=self.clock,
                monotonic=self.monotonic, sleep=self.sleep)
            self.stage = Stage.OFF_PROVED
            self.stage = Stage.LEASE_DISARMED
            if self.monotonic() >= deadline:
                raise TimeoutError("acceptance lifecycle bound exceeded before restore")
            self.stage = Stage.RESTORE_ALLOWED
            if self.restore_production() is not True:
                raise RuntimeError("production restore callback rejected")
            self.result = "PASS"
            return self.result
        except BaseException:
            self.stage = Stage.FAIL_CLOSED
            self.result = "FAIL_CLOSED"
            raise
        finally:
            self.lock.close()

    def _wait_child_death(self, deadline: float) -> None:
        while self.monotonic() < deadline:
            try:
                args, start, cgroup = _proc_identity(self.child.pid)
            except (FileNotFoundError, ProcessLookupError):
                return
            except RuntimeError as exc:
                if str(exc) != "child cmdline unavailable":
                    raise
                # Linux may expose an empty /proc/PID/cmdline during exit,
                # before procfs removes the PID.  That alone is NOT proof
                # that a process died: an otherwise live process with an
                # empty cmdline must remain a bounded, unresolved state.
                try:
                    stat_line = (Path("/proc") / str(self.child.pid) / "stat").read_text()
                except FileNotFoundError:
                    return
                tail = stat_line[stat_line.rfind(")") + 2:].split()
                if len(tail) < 20:
                    raise RuntimeError("child procfs stat incomplete") from exc
                state, start_time = tail[0], int(tail[19])
                if start_time != self.child.start_time:
                    raise RuntimeError("acceptance child PID was reused") from exc
                if state == "Z":
                    return
                # Empty cmdline with a live matching PID is not a successful
                # kill; wait for a zombie/disappearance within the deadline.
                self.sleep(min(0.05, max(0.0, deadline - self.monotonic())))
                continue
            if start != self.child.start_time or args != self.child.cmdline or cgroup != self.child.cgroup:
                raise RuntimeError("child identity changed while waiting for death")
            self.sleep(min(0.05, max(0.0, deadline - self.monotonic())))
        raise TimeoutError("killed acceptance child did not exit within bound")
