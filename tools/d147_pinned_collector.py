"""D147: pin existing D091 read-only collector outside replaceable app/.

A copy of the exact LIVE collector remains available during app/venv swaps.
No physical actuator, service stop, credential read, or dynamic update route.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path

ROOT = Path("/opt/services/rd6018-bot")
SOURCE = ROOT / "app/tools/node104_d091_physical_proof_collector.py"
SNAPSHOT_DIR = ROOT / "d147-proof"
SNAPSHOT = SNAPSHOT_DIR / "node104_d091_physical_proof_collector.py"
EXPECTED_SHA256 = "1127e9e3ba52a43ca97ddd8501ea4ac9a52887e708d725fd1299fd22d15a2398"


class CollectorPinError(RuntimeError):
    pass


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_regular(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CollectorPinError("collector path is not a regular file")
    return path.read_bytes()


def verify(snapshot: Path = SNAPSHOT) -> dict[str, object]:
    data = _read_regular(snapshot)
    if _digest(data) != EXPECTED_SHA256:
        raise CollectorPinError("pinned collector content drift")
    if snapshot.stat().st_mode & 0o022:
        raise CollectorPinError("collector must not be group/world writable")
    return {"schema":"D147_PINNED_D091_COLLECTOR_V1",
            "sha256":EXPECTED_SHA256, "bytes":len(data), "read_only":True}


def install(*, source: Path = SOURCE, destination: Path = SNAPSHOT,
            host_check=None) -> dict[str, object]:
    if host_check is None:
        from tools.node104_d090_transaction import production_host_check
        host_check = production_host_check
    host_check()
    if destination.exists() or destination.is_symlink():
        return verify(destination)
    data = _read_regular(source)
    if _digest(data) != EXPECTED_SHA256:
        raise CollectorPinError("live source collector differs from reviewed pin")
    parent = destination.parent
    if parent.is_symlink():
        raise CollectorPinError("collector parent is a symlink")
    if not parent.exists():
        parent.mkdir(mode=0o700)
    if not parent.is_dir() or parent.stat().st_mode & 0o022:
        raise CollectorPinError("collector directory unsafe")
    # O_EXCL prevents replacement; after creation never rewrite an existing pin.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o400)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    finally:
        pass
    dir_fd = os.open(parent, os.O_RDONLY)
    try: os.fsync(dir_fd)
    finally: os.close(dir_fd)
    return verify(destination)
