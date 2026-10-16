"""Opt-in detached parent/child plumbing for the D061 acceptance harness.

This module is inert on import. The parent owns the one global flock open file
description and passes that descriptor to its child. The child gate validates
that exact descriptor and inode; it never opens or relocks the lock path.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import subprocess
import math
import time
from typing import Iterator, Sequence

from .kill_supervisor import ADOPTION_CHECKS, ChildIdentity, GlobalLock, verify_child

LOCK_PATH = Path("/run/lock/rd6018-d061-physical-acceptance.lock")
LOCK_FD_ENV = "D061_PARENT_LOCK_FD"
PROOF_KEYS = frozenset({"schema", "epoch", "observed_monotonic", "child", "checks"})


def verify_live_adoption_proof(proof: object, child: ChildIdentity, *,
                               previous_epoch: int, now_monotonic: float,
                               max_age_s: float = 3.0) -> int:
    """Validate exact proof schema and per-check fresh evidence at action edge."""
    if not isinstance(proof, dict) or set(proof) != PROOF_KEYS or proof.get("schema") != "D061-adoption-proof/1":
        raise RuntimeError("adoption proof schema/key set mismatch")
    epoch, observed = proof.get("epoch"), proof.get("observed_monotonic")
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch <= previous_epoch:
        raise RuntimeError("adoption proof epoch is not strictly increasing")
    if isinstance(observed, bool) or not isinstance(observed, (int, float)) or not math.isfinite(observed):
        raise RuntimeError("invalid proof observation clock")
    if observed > now_monotonic or now_monotonic - observed > max_age_s:
        raise RuntimeError("adoption proof is stale or from the future")
    identity = proof.get("child")
    expected_identity = {"pid": child.pid, "start_time": child.start_time,
                         "cmdline": list(child.cmdline), "cgroup": child.cgroup,
                         "stage_sha256": child.stage_sha256}
    if identity != expected_identity:
        raise RuntimeError("adoption proof is not bound to the accepted child identity")
    checks = proof.get("checks")
    if not isinstance(checks, dict) or set(checks) != ADOPTION_CHECKS:
        raise RuntimeError("adoption proof must contain exact canonical 19 checks")
    for name in ADOPTION_CHECKS:
        evidence = checks[name]
        if not isinstance(evidence, dict) or set(evidence) != {"ok", "observed_monotonic"} or evidence["ok"] is not True:
            raise RuntimeError("invalid evidence record: " + name)
        timestamp = evidence["observed_monotonic"]
        if (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
                or not math.isfinite(timestamp) or timestamp > now_monotonic
                or now_monotonic - timestamp > max_age_s):
            raise RuntimeError("stale evidence record: " + name)
    return epoch


def inherited_parent_gate(*, lock_path: Path = LOCK_PATH):
    """Return a context manager proving child shares parent's locked inode."""
    raw = os.environ.get(LOCK_FD_ENV)
    if raw is None or not raw.isdecimal():
        raise RuntimeError("parent lock FD handoff missing")
    fd = int(raw)
    if fd < 3:
        raise RuntimeError("invalid inherited parent lock FD")
    held = os.fstat(fd)
    path = Path(lock_path).lstat()
    if (not stat.S_ISREG(held.st_mode) or stat.S_ISLNK(path.st_mode)
            or not stat.S_ISREG(path.st_mode)
            or (held.st_dev, held.st_ino) != (path.st_dev, path.st_ino)
            or held.st_uid != 0 or stat.S_IMODE(held.st_mode) != 0o600
            or path.st_uid != 0 or stat.S_IMODE(path.st_mode) != 0o600):
        raise RuntimeError("inherited parent lock inode/owner/mode mismatch")

    @contextmanager
    def gate() -> Iterator[None]:
        # The inherited descriptor refers to the same open file description;
        # closing this process copy cannot release the parent's reference.
        yield
    return gate


def install_pairing_gate(*, lock_path: Path = LOCK_PATH) -> None:
    """Install the FD adapter before calling the accepted takeover entrypoint."""
    from . import pairing
    pairing.node104_acceptance_gate = inherited_parent_gate(lock_path=lock_path)


def verify_child_at_action(identity: ChildIdentity, *, stage_file: Path) -> None:
    """Recheck PID/starttime/argv/cgroup and exact stage hash at action boundary."""
    verify_child(identity, stage_file=stage_file)


class DetachedChild:
    """Own the lock before spawn and retain it until the child has exited."""
    def __init__(self, lock_path: Path = LOCK_PATH):
        self.lock = GlobalLock(lock_path)
        self.process: subprocess.Popen[bytes] | None = None

    def start(self, argv: Sequence[str], *, env: dict[str, str] | None = None) -> subprocess.Popen[bytes]:
        if self.process is not None:
            raise RuntimeError("detached acceptance child already started")
        self.lock.acquire()
        assert self.lock.fd is not None
        child_env = dict(os.environ if env is None else env)
        child_env[LOCK_FD_ENV] = str(self.lock.fd)
        try:
            self.process = subprocess.Popen(list(argv), env=child_env,
                pass_fds=(self.lock.fd,), close_fds=True, start_new_session=True)
        except BaseException:
            self.lock.close()
            raise
        return self.process

    def join(self, timeout: float | None = None) -> int:
        if self.process is None:
            raise RuntimeError("detached acceptance child not started")
        try:
            return self.process.wait(timeout=timeout)
        finally:
            if self.process.poll() is not None:
                self.lock.close()

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            raise RuntimeError("cannot release parent lock while child is running")
        self.lock.close()
