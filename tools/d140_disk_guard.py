"""D140 conservative, read-only rollback capacity guard.

This guard accounts for an additional durable copy of both currently installed
app and venv on the same filesystem, plus a fixed reserve. It cannot authorize
a release by itself and never removes old backups or changes the device.
"""
from __future__ import annotations

import os
import ctypes
import shutil
from pathlib import Path

RESERVE_BYTES = 256 * 1024 * 1024
OVERHEAD_BYTES = 16 * 1024 * 1024


class CapacityBlocked(RuntimeError):
    pass


def _windows_allocated_bytes(path: Path) -> int:
    """Return Windows' allocated-on-disk size, failing closed on API errors."""
    if os.name != "nt":
        raise CapacityBlocked("Windows allocation API unavailable")
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_size = kernel32.GetCompressedFileSizeW
        get_size.argtypes = (ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong))
        get_size.restype = ctypes.c_ulong
        high = ctypes.c_ulong()
        ctypes.set_last_error(0)
        low = get_size(str(path), ctypes.byref(high))
        error = ctypes.get_last_error()
        if low == 0xFFFFFFFF and error:
            raise OSError(error, "GetCompressedFileSizeW failed", str(path))
        return (high.value << 32) | low
    except (AttributeError, OSError) as exc:
        raise CapacityBlocked("cannot reliably determine allocated file size") from exc


def _allocated_file_bytes(path: Path) -> int:
    if os.name == "nt":
        return _windows_allocated_bytes(path)
    try:
        return path.stat().st_blocks * 512
    except (AttributeError, OSError) as exc:
        raise CapacityBlocked("cannot reliably determine allocated file size") from exc


def allocated_bytes(root: Path) -> int:
    if root.is_symlink() or not root.is_dir():
        raise CapacityBlocked("installed component missing or symlinked")
    allocated = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            allocated += 4096
        elif path.is_file():
            allocated += _allocated_file_bytes(path)
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
        free = shutil.disk_usage(root).free
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
