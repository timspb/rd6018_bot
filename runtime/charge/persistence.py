"""Canonical charge-session persistence and restore owner."""

from __future__ import annotations

import json
import hashlib
import logging
import math
import os
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Tuple

from runtime.charge.session_atomic import (
    atomic_session_write, compare_replace_session, compare_delete_session, WriteStatus,
)
from runtime.charge.session_document_projection import (
    project_session_document,
)
from runtime.charge.start_pending import (
    START_PENDING_KEY,
    StartPendingAction,
    StartPendingResult,
    StartPendingStatus,
    _pending_start_document,
    begin_start_pending,
    finish_start_pending,
    read_start_pending,
)
from runtime.charge.terminal_intent import (
    DONE_COMPLETION_STORAGE,
    DONE_COMPLETION_TERMINAL,
    DONE_OUTPUT_ON,
    DONE_OUTPUT_OFF,
    TerminalPersistenceRequest,
)
from runtime.charge.restore_admission import (
    DONE_STATE_VERSION,
    _explicit_storage_outcome,
    restore_allows_auto_enable,
    INTERRUPTION_OWNER,
    INTERRUPTION_REASON,
    session_identity,
    validate_interruption_marker,
)

from runtime.charge.session_restore import (
    AGM_STAGES, ELAPSED_MAX_HOURS, MAX_STAGE_CURRENT, MIX_DONE_TIMER,
    SESSION_FILE, SESSION_MAX_AGE, SESSION_MAX_AGE_S,
    SESSION_START_MAX_AGE, SESSION_START_MAX_AGE_S,
    _normalize_terminal_done_document, restore_session,
)

logger = logging.getLogger("rd6018")


def read_canonical_session(path: str | Path) -> Mapping[str, Any] | None:
    """Read one canonical session snapshot without modifying state or file."""
    file = Path(path)
    try:
        if file.is_symlink() or not file.is_file():
            return None
        document = json.loads(file.read_text(encoding="utf-8"))
        return document if type(document) is dict else None
    except (OSError, UnicodeError, ValueError, TypeError):
        return None




def managed_storage_ownership_proven(
    host: Any, *, document: dict[str, Any] | None = None,
    session_file: str | None = None,
) -> bool:
    """Treat terminal Storage as owned only after exact durable session commit.

    RAM-only DONE or a prior SAFE_WAIT file is insufficient to keep an
    energized Output under managed authority. This function is read-only and
    never initiates or renews any physical command.
    """
    if not (
        getattr(host, "current_stage", None) == getattr(host, "STAGE_DONE", None)
        and bool(getattr(host, "_done_outcome_authoritative", False))
        and getattr(host, "_done_completion_kind", None) == DONE_COMPLETION_STORAGE
        and getattr(host, "_done_output_intent", None) == DONE_OUTPUT_ON
    ):
        return False

    if document is None:
        path = Path(SESSION_FILE if session_file is None else session_file)
        if path.is_symlink() or not path.is_file():
            return False
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
    if not isinstance(document, dict) or not _explicit_storage_outcome(document):
        return False

    sid = getattr(host, "_v2_trace_session_id", None)
    bid = getattr(host, "_v2_battery_id", None)
    if not (
        sid and bid
        and document.get("stage") == getattr(host, "STAGE_DONE", None)
        and document.get("v2_trace_session_id") == sid
        and document.get("v2_battery_id") == bid
        and document.get("terminal_session_id") == sid
        and isinstance(document.get("terminal_metadata"), dict)
        and document["terminal_metadata"].get("completion_kind") == DONE_COMPLETION_STORAGE
        and document["terminal_metadata"].get("output_intent") == DONE_OUTPUT_ON
    ):
        return False

    try:
        generation = float(getattr(host, "_v2_trace_started_at", None))
        recorded = float(document.get("v2_trace_started_at"))
    except (TypeError, ValueError, OverflowError):
        return False
    if not (math.isfinite(generation) and generation > 0
            and math.isfinite(recorded) and abs(generation - recorded) <= 1e-6):
        return False

    guard = getattr(host, "_main_current_guard", None)
    saved_guard = document.get("main_current_guard_v1")
    if (guard is None) != (saved_guard is None):
        return False
    if guard is not None:
        from runtime.charge.strategy.main_guard_session import read_guard
        try:
            restored, revision = read_guard(
                document, session_id=sid, battery_id=bid, now_s=time.time(),
            )
        except (ValueError, TypeError, OverflowError):
            return False
        if (
            saved_guard.get("snapshot") != guard.snapshot()
            or restored.pending is not None
            or restored.fault is not None
            or revision != getattr(host, "_main_current_guard_revision", None)
        ):
            return False
    return True


def paused_done_resume_is_authorized(
    app: Any,
    host: Any,
    *,
    session_file: Optional[str] = None,
) -> bool:
    """Guard operator-pause resume before a dormant Done session is restored."""
    session_file = SESSION_FILE if session_file is None else session_file
    pause_active = getattr(app, "_operator_pause_active", None)
    if not callable(pause_active) or not bool(pause_active()):
        return True
    if host.current_stage == host.STAGE_DONE:
        return restore_allows_auto_enable(host)
    if bool(getattr(host, "is_active", False)):
        return True
    if not os.path.exists(session_file):
        return True
    try:
        with open(session_file, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError):
        return True
    if document.get("stage") != host.STAGE_DONE:
        return True
    return _explicit_storage_outcome(document)







def enrich_restored_session(host: Any, document: dict[str, Any], *,
                            session_file: str = SESSION_FILE) -> bool:
    """Persist restored identity/continuations via the sole canonical writer.

    Start from the complete old document to retain extension and migration keys.
    Guarded documents are rejected before reaching this path by restore_session;
    complete_session_document still independently protects any guarded journal.
    """
    if not document or host.current_stage == host.STAGE_IDLE:
        return False
    saved_at = time.time()
    from runtime.charge.session_atomic import complete_session_document
    from runtime.charge.strategy.main_guard_session import GUARD_KEY, GuardJournalError
    if GUARD_KEY in document or getattr(host, "_main_current_guard", None) is not None:
        # Identity-only enrichment cannot claim a guarded checkpoint revision.
        return False
    try:
        completed = complete_session_document(
            host, document, previous=document, now_s=saved_at,
        )
    except GuardJournalError as exc:
        logger.error("Restored session identity/Guard reconciliation failed: %s", exc)
        return False
    try:
        atomic_session_write(session_file, completed, allow_nan=True)
    except OSError as exc:
        logger.error("Could not persist restored session identity: %s", exc)
        return False
    return True


def clear_session_file(host: Any, *, session_file: str = SESSION_FILE) -> None:
    """Delete the exact observed ordinary document under the shared writer lock."""
    try:
        raw = Path(session_file).read_bytes()
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.error("Session clear could not inspect canonical file: %s", exc)
        return
    status = compare_delete_session(session_file, raw)
    if status != "COMMITTED":
        logger.error("Session clear blocked by canonical compare-delete: %s", status)


def retire_controller_session(host: Any, *, session_id: str, battery_id: str | None,
                              off_transaction_id: str,
                              expected_document_sha256: str | None = None,
                              session_file: str = SESSION_FILE) -> bool:
    """Durably replace the exact active session with a non-restorable tombstone.

    Called only by explicit recovery clearance after verified OFF and under the
    app owner lock. The controller is made IDLE only after file+directory fsync.
    """
    path = Path(session_file)
    _raw, pending, pending_error = read_start_pending(path)
    if pending_error or pending is not None:
        return False
    raw = path.read_bytes()
    if expected_document_sha256 is not None:
        if hashlib.sha256(raw).hexdigest() != expected_document_sha256:
            return False
    current = json.loads(raw.decode("utf-8"))
    if not isinstance(current, dict) or current.get("state") == "retired":
        return False
    if not isinstance(off_transaction_id, str) or not off_transaction_id.strip():
        return False
    if (current.get("v2_trace_session_id") != session_id
            or current.get("v2_battery_id") != battery_id
            or current.get("stage") in (None, host.STAGE_IDLE)):
        return False
    current_stage = getattr(host, "current_stage", host.STAGE_IDLE)
    if current_stage != host.STAGE_IDLE and (
            current.get("stage") != current_stage
            or getattr(host, "_v2_trace_session_id", None) != session_id
            or getattr(host, "_v2_battery_id", None) != battery_id):
        return False
    tombstone = {
        "owner": "runtime.charge.persistence",
        "schema_version": 1,
        "state": "retired",
        "stage": "RETIRED",
        "retirement_kind": "operator_recovery_clearance",
        "output_intent": "verified_off",
        "verified_off_transaction_id": off_transaction_id.strip(),
        "verified_off_recorded_utc": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "battery_id": battery_id,
        "retired_utc": datetime.now(timezone.utc).isoformat(),
    }
    # Fence any same-process save/shutdown path before the durable replacement.
    # If a crash or fsync error occurs at a cut point, no later save may put the
    # old active document back over a possibly committed retirement marker.
    host._recovery_session_retirement_pending = True
    atomic_session_write(path, tombstone, allow_nan=False)
    with path.open("r", encoding="utf-8") as stream:
        written = json.load(stream)
    if written != tombstone:
        return False
    host._recovery_session_retired_id = session_id
    if current_stage != host.STAGE_IDLE:
        host.current_stage = host.STAGE_IDLE
        host._clear_restored_targets()
    return True



def save_session(
    host: Any, voltage: float, current: float, ah: float, *,
    session_file: str = SESSION_FILE,
    terminal_request: TerminalPersistenceRequest | None = None,
    restore_expected_bytes: bytes | None = None,
) -> tuple[WriteStatus, bytes | None] | None:
    """Сохранить текущее состояние в charge_session.json. Уставки — с прибора, если известны."""
    data = project_session_document(
        host, voltage, current, ah, session_file=session_file,
        terminal_request=terminal_request,
    )
    if data is None:
        if restore_expected_bytes is not None:
            raise RuntimeError(f"restore canonical commit failed: {WriteStatus.NOT_COMMITTED.value}")
        return
    from runtime.charge.session_atomic import atomic_session_write, compare_replace_session
    if restore_expected_bytes is not None:
        # A terminal DONE snapshot records the measurements at completion.
        # Live measurements supplied to startup restore are not a new terminal
        # event, so retain that evidence while enriching the same CAS document.
        try:
            restore_document = json.loads(restore_expected_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            restore_document = None
        if isinstance(restore_document, dict):
            # Keep legacy/extension fields that the current projection does not
            # own; known current fields remain governed by the canonical projection.
            for name, value in restore_document.items():
                data.setdefault(name, value)
            if (
                restore_document.get("stage") == getattr(host, "STAGE_DONE", None)
                and isinstance(restore_document.get("terminal_metadata"), dict)
                and isinstance(data.get("terminal_metadata"), dict)
            ):
                prior_metadata = restore_document["terminal_metadata"]
                terminal_metadata = data["terminal_metadata"]
                for name in ("voltage", "current", "ah", "availability"):
                    if name in prior_metadata:
                        terminal_metadata[name] = prior_metadata[name]
        status, observed = compare_replace_session(
            session_file, restore_expected_bytes, data,
            allow_nan=getattr(host, "_main_current_guard", None) is None,
        )
        if status is WriteStatus.COMMITTED:
            guard_record = data.get("main_current_guard_v1")
            if (getattr(host, "_main_current_guard", None) is not None
                    and isinstance(guard_record, dict)
                    and type(guard_record.get("revision")) is int):
                host._main_current_guard_revision = guard_record["revision"]
        return status, observed
    try:
        atomic_session_write(
            session_file, data,
            allow_nan=getattr(host, "_main_current_guard", None) is None,
        )
        guard_record = data.get("main_current_guard_v1")
        if (getattr(host, "_main_current_guard", None) is not None
                and isinstance(guard_record, dict)
                and type(guard_record.get("revision")) is int):
            # Keep the in-memory concurrency token aligned with this same
            # atomic canonical replacement. MAIN Guard admission uses it
            # to reject a stale owner if a newer ACK is already durable.
            host._main_current_guard_revision = guard_record["revision"]
    except OSError as ex:
        logger.warning("Could not save session: %s", ex)


def mark_session_interrupted(
    session_file: str,
    *,
    expected_document_sha256: str,
    expected_identity: Mapping[str, Any],
    recorded_at_utc: str,
) -> bool:
    """Atomically add an interruption marker without projecting mutable host state.

    Caller serializes this operation with the existing execution owner lock.
    """
    path = Path(session_file)
    try:
        _raw, pending, pending_error = read_start_pending(path)
        if pending_error or pending is not None:
            return False
        if path.is_symlink() or not path.is_file():
            return False
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_document_sha256:
            return False
        document = json.loads(raw.decode("utf-8"))
        if not isinstance(document, dict):
            return False
        identity = session_identity(document)
        if identity is None or identity != dict(expected_identity):
            return False
        classification = validate_interruption_marker(document)
        if classification == "blocked":
            return False
        if classification == "interrupted":
            return True
        updated = dict(document)
        updated["interruption_v1"] = {
            "schema_version": 1,
            "owner": INTERRUPTION_OWNER,
            "state": "interrupted",
            "reason": INTERRUPTION_REASON,
            "rearmable": False,
            "recorded_at_utc": recorded_at_utc,
            "session_identity": dict(expected_identity),
        }
        if validate_interruption_marker(updated) != "interrupted":
            return False
        atomic_session_write(path, updated)
        return True
    except Exception:
        return False


__all__ = [
    "DONE_COMPLETION_STORAGE",
    "DONE_COMPLETION_TERMINAL",
    "DONE_OUTPUT_OFF",
    "DONE_OUTPUT_ON",
    "DONE_STATE_VERSION",
    "SESSION_FILE",
    "SESSION_MAX_AGE_S",
    "SESSION_START_MAX_AGE_S",
    "clear_session_file",
    "mark_session_interrupted",
    "enrich_restored_session",
    "paused_done_resume_is_authorized",
    "restore_allows_auto_enable",
    "restore_session",
    "project_session_document",
    "save_session",
]
