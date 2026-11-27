"""One-write, crash-durable canonical session serialization.

This is the single secure atomic replacement primitive for the canonical
charge-session document, owned by runtime.charge.persistence. The execution
owner may call it for MAIN Guard checkpoints while holding its owner-wide lock.
Other callers must preserve that journal and never create a parallel writer.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
from enum import Enum
from typing import Any, Mapping

from rd6018_telemetry import CURRENT_SETPOINT_READBACK_TOLERANCE_A

_SESSION_WRITE_LOCK = threading.RLock()
_PENDING_KEY = "start_transaction_pending_v1"


class WriteStatus(str, Enum):
    COMMITTED = "COMMITTED"
    NOT_COMMITTED = "NOT_COMMITTED"
    OUTCOME_UNCERTAIN = "OUTCOME_UNCERTAIN"


def _ordinary_write_fence(target: Path) -> None:
    try:
        raw = target.read_bytes()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise PermissionError("canonical session cannot be safely inspected") from exc
    try:
        current = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise PermissionError("malformed canonical session is preserved") from exc
    if not isinstance(current, dict):
        raise PermissionError("unknown canonical session envelope is preserved")
    if any(str(key).startswith("start_transaction_") and key != "start_transaction_generation"
           for key in current):
        raise PermissionError("canonical START transaction fence is active or unknown")


def atomic_session_write(path: str | Path, document: Mapping[str, Any], *,
                         allow_nan: bool = True, _pending_transition: bool = False) -> None:
    with _SESSION_WRITE_LOCK:
        target = Path(path)
        if not _pending_transition:
            _ordinary_write_fence(target)
        _atomic_session_write_locked(target, document, allow_nan=allow_nan)


def _atomic_session_write_locked(path: str | Path, document: Mapping[str, Any], *,
                                 allow_nan: bool = True) -> bytes:
    target = Path(path)
    payload = json.dumps(
        dict(document), ensure_ascii=False, indent=2, allow_nan=allow_nan
    ).encode("utf-8")
    _atomic_bytes_replace_locked(target, payload)
    return payload


def _atomic_bytes_replace_locked(target: Path, payload: bytes) -> None:
    mode = None
    try:
        mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        pass
    fd, temp = tempfile.mkstemp(prefix=".charge-session-", suffix=".tmp",
                               dir=str(target.parent))
    try:
        if mode is not None:
            fchmod = getattr(os, "fchmod", None)
            if fchmod is None:
                os.chmod(temp, mode)
            else:
                fchmod(fd, mode)
        stream = os.fdopen(fd, "wb")
        fd = None  # fdopen now owns the descriptor and closes it on exit.
        with stream:
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
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if os.path.exists(temp):
            os.unlink(temp)


def compare_replace_session(path: str | Path, expected_bytes: bytes | None,
                            document: Mapping[str, Any], *,
                            allow_nan: bool = False,
                            transaction_id: str | None = None,
                            generation: int | None = None,
                            replacement_bytes: bytes | None = None) -> tuple[WriteStatus, bytes | None]:
    """CAS ordinary bytes, or a pending envelope when identity is supplied."""
    target = Path(path)
    payload = (replacement_bytes if replacement_bytes is not None else
               json.dumps(dict(document), ensure_ascii=False, indent=2,
                          allow_nan=allow_nan).encode("utf-8"))
    with _SESSION_WRITE_LOCK:
        try:
            current = target.read_bytes()
        except FileNotFoundError:
            current = None
        except OSError:
            return WriteStatus.OUTCOME_UNCERTAIN, None
        if current != expected_bytes:
            return WriteStatus.NOT_COMMITTED, current
        if transaction_id is None:
            if current is not None:
                try:
                    _ordinary_write_fence(target)
                except PermissionError:
                    return WriteStatus.NOT_COMMITTED, current
        else:
            try:
                envelope = json.loads(current.decode("utf-8"))
                pending = envelope[_PENDING_KEY]
                valid_identity = (pending.get("transaction_id") == transaction_id
                                  and pending.get("generation") == generation
                                  and pending.get("phase") == "START_PENDING")
            except (UnicodeError, ValueError, KeyError, TypeError, AttributeError):
                valid_identity = False
            if not valid_identity:
                return WriteStatus.NOT_COMMITTED, current
        if current == payload:
            # Exact preimage and candidate are the same bytes. The read above
            # proves both sides of the no-op CAS without touching the file.
            return WriteStatus.COMMITTED, current
        try:
            if replacement_bytes is None:
                _atomic_session_write_locked(target, document, allow_nan=allow_nan)
            else:
                _atomic_bytes_replace_locked(target, replacement_bytes)
        except OSError:
            pass
        try:
            observed = target.read_bytes()
        except OSError:
            return WriteStatus.OUTCOME_UNCERTAIN, None
        if observed == payload:
            return WriteStatus.COMMITTED, observed
        if observed == expected_bytes:
            return WriteStatus.NOT_COMMITTED, observed
        return WriteStatus.OUTCOME_UNCERTAIN, observed


def compare_delete_session(path: str | Path, expected_bytes: bytes, *,
                           transaction_id: str | None = None,
                           generation: int | None = None) -> str:
    """Unlink only the exact expected canonical bytes under the writer lock."""
    target = Path(path)
    with _SESSION_WRITE_LOCK:
        try:
            current = target.read_bytes()
        except FileNotFoundError:
            return WriteStatus.NOT_COMMITTED.value
        except OSError:
            return WriteStatus.OUTCOME_UNCERTAIN.value
        if current != expected_bytes:
            return WriteStatus.NOT_COMMITTED.value
        if transaction_id is not None:
            try:
                pending = json.loads(current.decode("utf-8"))[_PENDING_KEY]
                valid = (pending.get("transaction_id") == transaction_id
                         and pending.get("generation") == generation
                         and pending.get("phase") == "START_PENDING")
            except (UnicodeError, ValueError, KeyError, TypeError, AttributeError):
                valid = False
            if not valid:
                return WriteStatus.NOT_COMMITTED.value
        else:
            try:
                _ordinary_write_fence(target)
            except PermissionError:
                return WriteStatus.NOT_COMMITTED.value
        try:
            target.unlink()
        except OSError:
            try:
                return (WriteStatus.NOT_COMMITTED.value if target.read_bytes() == expected_bytes
                        else WriteStatus.OUTCOME_UNCERTAIN.value)
            except OSError:
                return WriteStatus.OUTCOME_UNCERTAIN.value
        try:
            directory = os.open(str(target.parent), os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            if os.name == "posix":
                return WriteStatus.OUTCOME_UNCERTAIN.value
        return (WriteStatus.NOT_COMMITTED.value if target.exists()
                else WriteStatus.COMMITTED.value)


def complete_session_document(host: Any, data: Mapping[str, Any],
                              *, previous: Mapping[str, Any] | None = None,
                              now_s: float) -> dict[str, Any]:
    """Finalize charge trace and optional guard in *one* document.

    There is no Guard authority unless the controller supplies a qualified
    guard object. If an existing guarded session loses that object, refuse
    to erase its journal. Caller must fail closed and reconcile hardware.
    """
    result = dict(data)
    # Production extension metadata is projected before the single canonical
    # replace. The extension owner mutates no persistence or controller object.
    from application.production_target_policy import is_production_host
    if is_production_host(host):
        from application.production_session_extensions import session_document_extensions
        extra = session_document_extensions(host, dict(result))
        if extra is not None:
            if not isinstance(extra, Mapping):
                raise TypeError("session document extension must return a mapping")
            result.update(extra)
    # A native recipe is a pinned *data* selection, never an execution grant.
    # Include it in the same canonical atomic session write (no sidecar).
    from runtime.charge.programs.native_recipe_session import (
        SESSION_KEY, native_selection_for_session,
    )
    selected = native_selection_for_session(
        host, profile=getattr(host, "battery_type", None),
        intent=getattr(host, "_v2_intent", None),
    )
    if selected is None:
        result.pop(SESSION_KEY, None)
    else:
        result[SESSION_KEY] = selected.to_document()
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
        else:
            result.pop("v2_recovery_safe_wait", None)
        if final is not None:
            result["v2_final_safe_wait"] = final.as_dict()
        else:
            result.pop("v2_final_safe_wait", None)
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
        saved_snapshot = saved.get("snapshot") if isinstance(saved, Mapping) else None
        if (isinstance(saved_snapshot, Mapping)
                and saved_snapshot.get("segment_id") != current.segment_id
                and getattr(host, "_main_current_guard_revision", None) != saved.get("revision")):
            raise GuardJournalError("desulfation_return_checkpoint_revision_changed")
        result[GUARD_KEY] = saved
        expected_revision = saved.get("revision")
    if result.get("stage") == getattr(host, "STAGE_MIX", None):
        # This is a continuation of the existing guarded session, not a new
        # grant. The previous durable stage must be MAIN or MIX, with the
        # same guarded identity and a fully resolved current ratchet.
        if prior.get("stage") not in {
            getattr(host, "STAGE_MAIN", None), getattr(host, "STAGE_MIX", None)
        } or saved is None or current.pending is not None:
            raise GuardJournalError("mix_guard_handoff_requires_resolved_main")
    # Persisting a guarded MAIN session with a wider target would let a later
    # normal stage tick reprogram Iset above the physical ratchet. Reject the
    # entire document, including every unrelated periodic save, rather than
    # silently blessing a conflicting current setpoint.
    if result.get("stage") == getattr(host, "STAGE_MAIN", None):
        try:
            target_i = float(result["target_current"])
        except (KeyError, TypeError, ValueError, OverflowError):
            raise GuardJournalError("guarded_main_target_unavailable") from None
        from math import isfinite
        if (not isfinite(target_i) or target_i <= 0
                or target_i > current.hardware_limit_a + CURRENT_SETPOINT_READBACK_TOLERANCE_A):
            raise GuardJournalError("guarded_main_target_exceeds_ratchet")
    return attach_guard(result, current, now_s=now_s,
                        expected_revision=expected_revision)


__all__ = [
    "WriteStatus", "atomic_session_write", "compare_replace_session",
    "complete_session_document",
]
