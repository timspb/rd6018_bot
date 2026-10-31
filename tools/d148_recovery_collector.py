"""D148: pin the D138 state-preserving recovery observer outside swappable app/.

The D147 observer is retained unchanged; this is a separate reviewed D138
collector with explicit recovery-mode support. No collector may operate a
charger; installation itself only copies a verified local Python source.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import os

ROOT = Path("/opt/services/rd6018-bot")
CANDIDATE_SOURCE = Path("/tmp/d138_stage_d351c208/tree/tools/node104_d091_physical_proof_collector.py")
DEST = ROOT / "d147-proof/d148_recovery_d091_collector.py"
D138_SHA256 = "a738f08e5554fa70188af856bc359b198838a983394948aaee8c64fdd9df1e95"
D147_SHA256 = "1127e9e3ba52a43ca97ddd8501ea4ac9a52887e708d725fd1299fd22d15a2398"
D147 = ROOT / "d147-proof/node104_d091_physical_proof_collector.py"


class RecoveryCollectorError(RuntimeError):
    pass


def verify(source: Path = DEST, *, expected: str | None = None) -> dict:
    if expected is None:
        expected = D138_SHA256
    if (source.is_symlink() or not source.is_file()
            or source.parent.is_symlink()
            or source.parent.stat().st_mode & 0o022
            or source.stat().st_mode & 0o222):
        raise RecoveryCollectorError("recovery collector location or permissions unsafe")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != expected:
        raise RecoveryCollectorError("recovery collector SHA-256 mismatch")
    return {"schema": "D148_RECOVERY_D091_PIN_V1", "sha256": digest,
            "supports_state_preserving_recovery": True, "read_only": True}


def install(source: Path = CANDIDATE_SOURCE, dest: Path = DEST,
            old_pin: Path = D147, *, host_check=None) -> dict:
    if host_check is None:
        from node104_d090_transaction import production_host_check
        host_check = production_host_check
    host_check()
    if verify_old_hash(old_pin) != D147_SHA256:
        raise RecoveryCollectorError("previously installed D147 collector changed")
    if dest.exists() or dest.is_symlink():
        return verify(dest)
    if source.is_symlink() or not source.is_file():
        raise RecoveryCollectorError("untrusted recovery collector source")
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != D138_SHA256:
        raise RecoveryCollectorError("recovery collector source not reviewed D138")
    parent = dest.parent
    if (parent.is_symlink() or not parent.is_dir()
            or parent.stat().st_mode & 0o022):
        raise RecoveryCollectorError("recovery collector destination unsafe")
    fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o400)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    directory_fd = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return verify(dest)


def verify_old_hash(old_pin: Path) -> str:
    if (old_pin.is_symlink() or not old_pin.is_file()
            or old_pin.stat().st_mode & 0o222):
        raise RecoveryCollectorError("D147 original pin unavailable")
    return hashlib.sha256(old_pin.read_bytes()).hexdigest()
