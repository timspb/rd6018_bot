"""One-write, crash-durable canonical session serialization.

This is owned by the controller, not an observer or independent process.
The caller must serialize all charge and guard lifecycle updates under ONE
owner-wide lock before active MAIN Guard actuation can be enabled.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Mapping


def atomic_session_write(path: str | Path, document: Mapping[str, Any], *,
                         allow_nan: bool = True) -> None:
    target = Path(path)
    payload = json.dumps(
        dict(document), ensure_ascii=False, indent=2, allow_nan=allow_nan
    ).encode("utf-8")
    mode = None
    try:
        mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        pass
    fd, temp = tempfile.mkstemp(prefix=".charge-session-", suffix=".tmp",
                               dir=str(target.parent))
    try:
        if mode is not None:
            os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, target)
        # The file replacement is atomic; sync directory metadata on Linux.
        try:
            directory = os.open(str(target.parent), os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            # Windows cannot reliably fsync a directory. Production is Linux.
            if os.name == "posix":
                raise
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def complete_session_document(host: Any, data: Mapping[str, Any],
                              *, previous: Mapping[str, Any] | None = None,
                              now_s: float) -> dict[str, Any]:
    """Finalize charge trace and optional guard in *one* document.

    There is no Guard authority unless the controller supplies a qualified
    guard object. If an existing guarded session loses that object, refuse
    to erase its journal. Caller must fail closed and reconcile hardware.
    """
    result = dict(data)
    session_id = getattr(host, "_v2_trace_session_id", None)
    started = getattr(host, "_v2_trace_started_at", None)
    battery_id = getattr(host, "_v2_battery_id", None)
    if session_id and started and float(started) > 0:
        result["v2_trace_session_id"] = str(session_id)
        result["v2_trace_started_at"] = float(started)
        result["v2_battery_id"] = battery_id
        intent = getattr(host, "_v2_intent", None)
        condition = getattr(host, "_v2_condition_before", None)
        result["v2_intent"] = str(getattr(intent, "value", intent))
        result["v2_condition_before"] = str(getattr(condition, "value", condition))
        result["v2_authoritative"] = True
        recovery = getattr(host, "_recovery_safe_wait", None)
        final = getattr(host, "_final_safe_wait", None)
        if recovery is not None:
            result["v2_recovery_safe_wait"] = recovery.as_dict()
        if final is not None:
            result["v2_final_safe_wait"] = final.as_dict()
        if result.get("stage") == getattr(host, "STAGE_DONE", None):
            result["terminal_session_id"] = str(session_id)

    # Existing guard journal belongs to this session until an explicit
    # verified retirement; neither an ordinary save nor restart may erase it.
    prior = dict(previous or {})
    from runtime.charge.strategy.main_guard_session import (
        GUARD_KEY, GuardJournalError, attach_guard
    )
    saved = prior.get(GUARD_KEY)
    current = getattr(host, "_main_current_guard", None)
    if current is None:
        if saved is not None:
            raise GuardJournalError("existing_guard_not_restored_to_owner")
        return result
    if not session_id or not battery_id:
        raise GuardJournalError("guard_requires_real_trace_identity")
    expected_revision = 0
    if saved is not None:
        # Never copy a previous battery's guard into a new session.
        if (prior.get("v2_trace_session_id") != session_id
                or prior.get("v2_battery_id") != battery_id):
            raise GuardJournalError("stale_guard_from_different_session")
        result[GUARD_KEY] = saved
        expected_revision = saved.get("revision")
    return attach_guard(result, current, now_s=now_s,
                        expected_revision=expected_revision)


__all__ = ["atomic_session_write", "complete_session_document"]
