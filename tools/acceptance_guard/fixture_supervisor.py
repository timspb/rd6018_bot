"""Hardware-inert D061 supervisor/child protocol fixture.

This module is deliberately not wired to the accepted node104 runner, a service,
or any physical adapter. It exists to test lock and evidence semantics offline.
"""
from __future__ import annotations

import errno
import fcntl
import hashlib
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class Disposition(str, Enum):
    HOLD = "HOLD"
    OFF_PROVED = "OFF_PROVED"
    LEASE_DISARMED = "LEASE_DISARMED"


@dataclass(frozen=True)
class FixtureChild:
    pid: int
    argv: tuple[str, ...]
    start_ticks: int
    cgroup: str
    source_sha256: str


def _identity(pid: int, proc_root: Path = Path("/proc")) -> tuple[tuple[str, ...], int, str]:
    root = Path(proc_root) / str(pid)
    argv = tuple(part.decode("utf-8", "strict") for part in (root / "cmdline").read_bytes().split(b"\0") if part)
    fields = (root / "stat").read_text().split(")", 1)[1].split()
    # /proc/PID/stat field 22; fields start at field 3 after comm.
    start_ticks = int(fields[19])
    return argv, start_ticks, (root / "cgroup").read_text()


class FixtureSupervisor:
    """Parent-owned flock; launches only a named synthetic child script."""

    def __init__(self, lock_path: Path, *, owner_uid: int | None = None):
        self.lock_path = Path(lock_path)
        self.owner_uid = os.getuid() if owner_uid is None else owner_uid
        self.fd: int | None = None
        self.child: subprocess.Popen[bytes] | None = None
        self.identity: FixtureChild | None = None

    def acquire(self) -> None:
        before = self.lock_path.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != self.owner_uid
                or stat.S_IMODE(before.st_mode) != 0o600):
            raise RuntimeError("fixture lock owner/type/mode mismatch")
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
        try:
            after = os.fstat(fd)
            if ((before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                    or after.st_uid != self.owner_uid or stat.S_IMODE(after.st_mode) != 0o600):
                raise RuntimeError("fixture lock inode changed")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd

    def start_synthetic_child(self, script: Path) -> FixtureChild:
        if self.fd is None:
            raise RuntimeError("supervisor must own the global lock before child launch")
        if self.child is not None:
            raise RuntimeError("duplicate acceptance child refused")
        script = Path(script).resolve()
        if script.name != "synthetic_child.py":
            raise RuntimeError("fixture supervisor only launches synthetic_child.py")
        digest = hashlib.sha256(script.read_bytes()).hexdigest()
        lock_stat = os.fstat(self.fd)
        ready = script.parent / "synthetic_child.ready"
        if ready.exists():
            raise RuntimeError("stale fixture ready marker refused")
        # NEVER inherit the supervisor's locked open file description.
        # flock(LOCK_UN) by a child sharing that description could unlock the
        # parent's exclusive lock. Child receives only path/inode identity.
        self.child = subprocess.Popen([sys.executable, str(script), str(self.lock_path),
                                       str(lock_stat.st_dev), str(lock_stat.st_ino), str(ready)],
                                      close_fds=True)
        end = time.monotonic() + 2.0
        while not ready.exists() and self.child.poll() is None and time.monotonic() < end:
            time.sleep(0.005)
        if not ready.exists():
            self.child.kill()
            self.child.wait(timeout=2)
            self.child = None
            raise RuntimeError("synthetic child inode-identity handshake failed")
        argv, start, cgroup = _identity(self.child.pid)
        self.identity = FixtureChild(self.child.pid, argv, start, cgroup, digest)
        self.verify_child(script)
        return self.identity

    def verify_child(self, script: Path) -> None:
        if self.child is None or self.identity is None:
            raise RuntimeError("synthetic child identity is absent")
        current = _identity(self.identity.pid)
        expected = (self.identity.argv, self.identity.start_ticks, self.identity.cgroup)
        if current != expected:
            raise RuntimeError("synthetic child PID/start/argv/cgroup identity mismatch")
        if hashlib.sha256(Path(script).read_bytes()).hexdigest() != self.identity.source_sha256:
            raise RuntimeError("synthetic child source SHA changed")

    def kill_synthetic_child(self, script: Path) -> None:
        self.verify_child(script)
        assert self.child is not None
        os.kill(self.child.pid, signal.SIGKILL)
        self.child.wait(timeout=2)
        # The parent descriptor must continue owning the original inode.
        self.assert_lock_held()

    def assert_lock_held(self) -> None:
        if self.fd is None:
            raise RuntimeError("supervisor lock descriptor is closed")
        contender = os.open(self.lock_path, os.O_RDWR)
        try:
            try:
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in (errno.EAGAIN, errno.EACCES):
                    return
                raise
            raise RuntimeError("supervisor failed to retain the global lock")
        finally:
            os.close(contender)

    def close(self) -> None:
        if self.child is not None and self.child.poll() is None:
            raise RuntimeError("cannot close supervisor while child is running")
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


@dataclass(frozen=True)
class Readback:
    source: str
    report_id: str
    observed_monotonic: float
    output_on: bool
    voltage: float
    current: float
    protection: str


@dataclass(frozen=True)
class LeaseReadback:
    source: str
    report_id: str
    observed_monotonic: float
    armed: bool


def _fresh(timestamp: object, now: float, max_age_s: float) -> bool:
    return (isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool)
            and math.isfinite(float(timestamp)) and 0 <= now - float(timestamp) <= max_age_s)


def verify_independent_off(first: Readback, second: Readback, *, now: float,
                           max_age_s: float = 3.0) -> bool:
    """Pure contract: distinct fresh sources must report OFF, zero V/A, NORMAL."""
    if first.source == second.source or first.report_id == second.report_id:
        return False
    for report in (first, second):
        if (not _fresh(report.observed_monotonic, now, max_age_s)
                or report.output_on is not False or report.protection != "NORMAL"):
            return False
        for value in (report.voltage, report.current):
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(float(value)) or abs(float(value)) > 0.02):
                return False
    return True


def off_then_disarm(*, first: Readback, second: Readback,
                    disarm: Callable[[float], object],
                    lease_readback: Callable[[float], LeaseReadback], now: Callable[[], float],
                    deadline: float, max_age_s: float = 3.0) -> Disposition:
    """Fixture transaction; disarm is unreachable until dual fresh OFF proof."""
    if not math.isfinite(deadline) or deadline <= 0 or deadline > 45.0:
        raise ValueError("fixture deadline must be in (0, 45] seconds")
    started = now()
    cutoff = started + deadline
    if not verify_independent_off(first, second, now=started, max_age_s=max_age_s):
        return Disposition.HOLD
    if now() >= cutoff or disarm(cutoff) is not True or now() >= cutoff:
        return Disposition.HOLD
    lease = lease_readback(cutoff)
    observed = now()
    if (not isinstance(lease, LeaseReadback) or lease.source in {first.source, second.source}
            or not _fresh(lease.observed_monotonic, observed, max_age_s)
            or lease.armed is not False or observed >= cutoff):
        return Disposition.HOLD
    return Disposition.LEASE_DISARMED
