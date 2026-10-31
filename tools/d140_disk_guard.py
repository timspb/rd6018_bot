"""D140 conservative, read-only rollback capacity guard.

This guard accounts for an additional durable copy of both currently installed
app and venv on the same filesystem, plus a fixed reserve. It cannot authorize
a release by itself and never removes old backups or changes the device.
"""
from __future__ import annotations

import os
from pathlib import Path

RESERVE_BYTES = 256 * 1024 * 1024
OVERHEAD_BYTES = 16 * 1024 * 1024


class CapacityBlocked(RuntimeError):
    pass


def allocated_bytes(root: Path) -> int:
    if root.is_symlink() or not root.is_dir():
        raise CapacityBlocked("installed component missing or symlinked")
    allocated = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            allocated += 4096
        elif path.is_file():
            allocated += path.stat().st_blocks * 512
        elif not path.is_dir():
            raise CapacityBlocked("special entry prevents reliable rollback sizing")
    return allocated


def assess(root: Path, candidate: Path, *, disk_usage=None) -> dict[str, int | bool | str]:
    if root.is_symlink() or not root.is_dir() or candidate.is_symlink() or not candidate.is_dir():
        raise CapacityBlocked("root or candidate unsafe")
    if (root / "app").stat().st_dev != (root / "venv").stat().st_dev:
        raise CapacityBlocked("live app and venv not on the same filesystem")
    if candidate.stat().st_dev != root.stat().st_dev:
        raise CapacityBlocked("candidate and live root are on different filesystems")
    app = allocated_bytes(root / "app")
    venv = allocated_bytes(root / "venv")
    copy = app + venv
    minimum = copy + RESERVE_BYTES + OVERHEAD_BYTES
    # It is intentionally conservative: no hardlink, sparse file, or CoW
    # saving is assumed. Free capacity is sampled immediately before action.
    if disk_usage is None:
        stats = os.statvfs(root)
        free = stats.f_bavail * stats.f_frsize
    else:
        free = int(disk_usage(root).free)
    return {
        "schema": "D140_DISK_CAPACITY_V1",
        "app_allocated_bytes": app,
        "venv_allocated_bytes": venv,
        "backup_required_bytes": copy,
        "reserve_bytes": RESERVE_BYTES,
        "overhead_bytes": OVERHEAD_BYTES,
        "minimum_free_bytes": minimum,
        "observed_free_bytes": free,
        "capacity_pass": free >= minimum,
    }


def require_capacity(root: Path, candidate: Path, *, disk_usage=None) -> dict[str, int | bool | str]:
    evidence = assess(root, candidate, disk_usage=disk_usage)
    if not evidence["capacity_pass"]:
        raise CapacityBlocked(
            "D140 rollback capacity insufficient before service stop: "
            f"free={evidence['observed_free_bytes']} required={evidence['minimum_free_bytes']}"
        )
    return evidence
