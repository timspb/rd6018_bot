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

from charging_log import log_session_header
from runtime.charge.runtime.variables import STAGE_CLOCK_SANITY_MAX_HOURS
from runtime.charge.strategy.main_variables import AGM_STAGE_VOLTAGES_V
from runtime.charge.strategy.mix_variables import mix_finish_hold_seconds
from runtime.safety.variables import MAX_STAGE_CURRENT_A
from runtime.safety.voltage_variables import clamp_pb_automatic_target_voltage
from runtime.charge.session_atomic import (
    atomic_session_write, compare_replace_session, compare_delete_session, WriteStatus,
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
from runtime.charge.session import restore_stage_history
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
from runtime.charge.restore_projection import (
    project_restore_scalars,
    project_restore_stage_timeline,
)
from runtime.charge.restore_finalization import finalize_restored_session


logger = logging.getLogger("rd6018")

SESSION_FILE = "charge_session.json"
SESSION_MAX_AGE_S = 24 * 60 * 60
SESSION_START_MAX_AGE_S = 24 * 60 * 60

SESSION_MAX_AGE = SESSION_MAX_AGE_S
SESSION_START_MAX_AGE = SESSION_START_MAX_AGE_S
AGM_STAGES = tuple(float(value) for value in AGM_STAGE_VOLTAGES_V.default)
MAX_STAGE_CURRENT = float(MAX_STAGE_CURRENT_A.default)
MIX_DONE_TIMER = mix_finish_hold_seconds()
ELAPSED_MAX_HOURS = float(STAGE_CLOCK_SANITY_MAX_HOURS.default)


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


def _set_done_outcome(
    host: Any,
    completion_kind: Optional[str],
    output_intent: str,
    *,
    authoritative: bool,
) -> None:
    host._done_completion_kind = completion_kind
    host._done_output_intent = output_intent
    host._done_outcome_authoritative = bool(authoritative)


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





def _normalize_terminal_done_document(
    host: Any,
    document: dict[str, Any],
    *,
    session_file: str,
) -> bool:
    """Normalize ambiguous legacy Done to terminal/OFF without rewriting evidence."""

    normalized = dict(document)
    normalized["done_state_version"] = DONE_STATE_VERSION
    normalized["completion_kind"] = DONE_COMPLETION_TERMINAL
    normalized["output_intent"] = DONE_OUTPUT_OFF

    terminal_metadata = normalized.get("terminal_metadata")
    if isinstance(terminal_metadata, dict):
        terminal_metadata = dict(terminal_metadata)
        terminal_metadata["completion_kind"] = DONE_COMPLETION_TERMINAL
        terminal_metadata["output_intent"] = DONE_OUTPUT_OFF
        normalized["terminal_metadata"] = terminal_metadata

    from runtime.charge.session_atomic import complete_session_document
    normalized = complete_session_document(
        host, normalized, previous=document, now_s=time.time(),
    )
    document.clear()
    document.update(normalized)
    return True


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
        import hashlib
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

def project_session_document(
    host: Any, voltage: float, current: float, ah: float, *,
    session_file: str = SESSION_FILE,
    terminal_request: TerminalPersistenceRequest | None = None,
    now_s: float | None = None,
) -> dict[str, Any] | None:
    """Return the canonical candidate without changing file bytes.

    Compatibility note: existing ``_done_*`` normalization is applied to the
    host because terminal metadata consumes those fields. This is the only host
    mutation. ``now_s`` supports deterministic projection; production callers
    omit it.
    """
    if bool(getattr(host, "_recovery_session_retirement_pending", False)):
        logger.error("Session save blocked while recovery retirement outcome is uncertain")
        return
    _raw, pending, pending_error = read_start_pending(session_file)
    if pending_error or pending is not None:
        logger.error("Session save blocked by START_PENDING fence: %s", pending_error or "pending")
        return
    if host.current_stage == host.STAGE_IDLE:
        return

    if host.current_stage == host.STAGE_DONE:
        if terminal_request is not None:
            _set_done_outcome(
                host,
                terminal_request.completion_kind,
                terminal_request.output_intent,
                authoritative=True,
            )
        elif not bool(getattr(host, "_done_outcome_authoritative", False)):
            _set_done_outcome(
                host,
                DONE_COMPLETION_TERMINAL,
                DONE_OUTPUT_OFF,
                authoritative=True,
            )
    else:
        _set_done_outcome(host, None, DONE_OUTPUT_OFF, authoritative=False)

    done_storage = bool(
        host.current_stage == host.STAGE_DONE
        and getattr(host, "_done_outcome_authoritative", False)
        and getattr(host, "_done_completion_kind", None) == DONE_COMPLETION_STORAGE
        and getattr(host, "_done_output_intent", DONE_OUTPUT_OFF) == DONE_OUTPUT_ON
    )
    target_finish = host._get_target_finish_time()
    if done_storage:
        uv, ui = host._storage_target()
        target_finish = None
    elif host.current_stage == host.STAGE_SAFE_WAIT:
        uv, ui = host._safe_wait_target_v, host._safe_wait_target_i
    elif host.current_stage == host.STAGE_COOLING:
        uv, ui = host._cooling_target_v, host._cooling_target_i
    else:
        uv, ui = host._get_target_v_i()
    # Сохраняем фактические уставки прибора (до потери связи/перезапуска).
    # Explicit Storage Done is the exception: the queued Storage target is
    # authoritative even when the last physical readback is still the old HV program.
    if (
        not done_storage
        and host._device_set_voltage is not None
        and host._device_set_voltage > 0
        and host._device_set_current is not None
        and host._device_set_current > 0
    ):
        uv, ui = host._device_set_voltage, host._device_set_current
    elif not done_storage:
        # С прибора уставки не приходили — не перезаписывать дефолтами профиля; сохранить из файла, если есть
        if os.path.exists(session_file):
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    old = json.load(f)
                tv, ti = float(old.get("target_voltage", 0) or 0), float(old.get("target_current", 0) or 0)
                if tv > 0 and ti > 0:
                    uv, ui = tv, ti
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
    previous_terminal_metadata = {}
    previous_document = {}
    if os.path.exists(session_file):
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                previous_document = json.load(f)
            if isinstance(previous_document, dict) and isinstance(
                previous_document.get("terminal_metadata"), dict
            ):
                previous_terminal_metadata = previous_document["terminal_metadata"]
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    def terminal_measurement(name: str, value: Any) -> Tuple[Optional[float], bool]:
        """Keep only evidenced positive measurements; never replace them with defaults."""
        try:
            candidate = float(value)
        except (TypeError, ValueError, OverflowError):
            candidate = 0.0
        if math.isfinite(candidate) and candidate > 0.0:
            return candidate, True
        try:
            previous = float(previous_terminal_metadata.get(name))
        except (TypeError, ValueError, OverflowError):
            previous = 0.0
        if math.isfinite(previous) and previous > 0.0:
            return previous, True
        return None, False

    saved_at = time.time() if now_s is None else float(now_s)
    terminal = host.current_stage == host.STAGE_DONE
    if terminal_request is not None and terminal:
        voltage, current, ah = (
            terminal_request.voltage_v,
            terminal_request.current_a,
            terminal_request.ah,
        )
    terminal_voltage, terminal_voltage_available = terminal_measurement("voltage", voltage)
    terminal_current, terminal_current_available = terminal_measurement("current", current)
    terminal_ah, terminal_ah_available = terminal_measurement("ah", ah)
    data = {
        "profile": host.battery_type,
        "stage": host.current_stage,
        "stage_start_time": host.stage_start_time,
        "target_finish_time": target_finish,
        "finish_timer_start": host.finish_timer_start,
        "ah_limit": host.ah_capacity,
        "start_ah": host._start_ah,
        "stage_start_ah": host._stage_start_ah,
        "stage_start_voltage": host._stage_start_voltage,
        "stage_start_current": host._stage_start_current,
        "stage_start_temp": host._stage_start_temp,
        "current_retries": host.antisulfate_count,
        "target_voltage": uv,
        "target_current": ui,
        "agm_stage_idx": host._agm_stage_idx,
        "safe_wait_next_stage": host._safe_wait_next_stage,
        "safe_wait_target_v": host._safe_wait_target_v,
        "safe_wait_target_i": host._safe_wait_target_i,
        "safe_wait_start": host._safe_wait_start,
        "total_start_time": host.total_start_time,  # v2.6: сохраняем общий старт
        "first_stage_hold_since": host._first_stage_hold_since,
        "first_stage_hold_current": host._first_stage_hold_current,
        "stuck_current_since": host._stuck_current_since,
        "stuck_current_value": host._stuck_current_value,
        "previous_stage": host.previous_stage,
        "last_transition_reason": host._last_transition_reason,
        "stage_history": list(host._stage_history),
        "saved_at": saved_at,
        "terminal_state_at": host.stage_start_time if terminal else None,
        "terminal_session_id": getattr(host, "_v2_trace_session_id", None) if terminal else None,
        "done_state_version": DONE_STATE_VERSION if terminal else None,
        "completion_kind": (
            getattr(host, "_done_completion_kind", DONE_COMPLETION_TERMINAL)
            if terminal
            else None
        ),
        "output_intent": (
            getattr(host, "_done_output_intent", DONE_OUTPUT_OFF)
            if terminal
            else None
        ),
        "terminal_metadata": {
            "stage": host.STAGE_DONE,
            "reason": host._last_transition_reason,
            "completion_kind": getattr(
                host, "_done_completion_kind", DONE_COMPLETION_TERMINAL
            ),
            "output_intent": getattr(host, "_done_output_intent", DONE_OUTPUT_OFF),
            "voltage": terminal_voltage,
            "current": terminal_current,
            "ah": terminal_ah,
            "availability": {
                "voltage": terminal_voltage_available,
                "current": terminal_current_available,
                "ah": terminal_ah_available,
            },
        } if terminal else None,
    }
    # The trace identity and optional MAIN Guard checkpoint must be in
    # the *same atomic write*, never a later independent patch of this JSON.
    # GuardJournalError is intentionally not swallowed: unsafe loss of a
    # prior guarded checkpoint must reach the owner's fail-closed path.
    from runtime.charge.session_atomic import (
        complete_session_document,
    )
    data = complete_session_document(
        host, data, previous=previous_document, now_s=saved_at,
    )
    return data


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

def restore_session(
    host: Any,
    voltage: float,
    current: float,
    ah: float,
    *,
    session_file: str = SESSION_FILE,
    _guarded_activation_permit: Any = None,
) -> Tuple[bool, Optional[str]]:
        """
        Восстановить сессию из файла, если прошло < 60 мин.
        Возвращает (ok, notify_message).
        """
        if not os.path.exists(session_file):
            return False, None
        try:
            raw_bytes = Path(session_file).read_bytes()
            raw_document = raw_bytes.decode("utf-8")
            data = json.loads(raw_document)
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False, None

        if not isinstance(data, dict):
            return False, None
        if _pending_start_document(data):
            return False, "A START transaction envelope requires reconciliation; automatic restore is disabled."
        interruption = validate_interruption_marker(data)
        if interruption == "interrupted":
            return False, "This charge session was interrupted by process restart; automatic restore is disabled."
        if interruption == "blocked":
            return False, "Interruption marker is invalid; automatic restore is disabled."
        # Verify optional immutable native recipe selection *before* restoring
        # any controller fields. A corrupted or wrong-profile snapshot cannot
        # silently become a normal AUTO session.
        from runtime.charge.programs.native_recipe_session import (
            restore_native_selection,
        )
        try:
            selected_native = restore_native_selection(
                data, profile=data.get("profile"), intent=data.get("v2_intent"),
            )
        except (ValueError, TypeError, KeyError) as exc:
            return False, f"Native recipe session selection invalid: {exc}"
        # A recovery-retired record is terminal evidence, never an old session.
        # Reject before mutating any controller fields.
        if data.get("owner") == "runtime.charge.persistence" and data.get("state") == "retired":
            if (data.get("schema_version") == 1 and data.get("stage") == "RETIRED"
                    and data.get("retirement_kind") == "operator_recovery_clearance"
                    and data.get("output_intent") == "verified_off"
                    and data.get("verified_off_transaction_id")
                    and data.get("verified_off_recorded_utc")
                    and data.get("session_id") and "battery_id" in data and data.get("retired_utc")):
                return False, "This charge session was explicitly retired; start a fresh session."
            return False, "Retired session record is invalid; automatic restore is disabled."
        # Guarded MAIN snapshots carry monotone electrical authority. They
        # remain quarantined unless the canonical startup owner supplies its
        # one-transaction, current-task activation capability.
        from runtime.charge.strategy.main_guard_session import GUARD_KEY
        if GUARD_KEY in data:
            from runtime.charge.session import (
                GuardedRestoreCandidate,
                _valid_guarded_restore_activation_permit,
            )
            from runtime.charge.strategy.main_guard_session import GuardJournalError, read_guard
            try:
                sid = str(data.get("v2_trace_session_id") or "")
                bid = str(data.get("v2_battery_id") or "")
                restored_guard, revision = read_guard(
                    data, session_id=sid, battery_id=bid, now_s=time.time(),
                )
            except (GuardJournalError, ValueError, TypeError, OverflowError):
                restored_guard, revision = None, None
            permit_valid = (
                restored_guard is not None and restored_guard.pending is None
                and restored_guard.fault is None
                and _valid_guarded_restore_activation_permit(
                    _guarded_activation_permit, document=data, session_id=sid,
                    battery_id=bid, revision=revision,
                    candidate=getattr(host, "_guarded_restore_candidate", None),
                    canonical_bytes_sha256=hashlib.sha256(raw_bytes).hexdigest(),
                )
            )
            if not permit_valid:
                host._guarded_restore_candidate = GuardedRestoreCandidate.capture(
                    data, "direct_native_pre_on_reconciliation_required",
                    canonical_bytes=raw_bytes,
                )
                return False, (
                    "MAIN Current Guard session is held for owner/readback "
                    "reconciliation; automatic resume is disabled."
                )
        saved_at = data.get("saved_at", 0)
        if time.time() - saved_at > SESSION_MAX_AGE:
            host._clear_session_file()
            return False, None

        scalars = project_restore_scalars(
            data, ah=ah, voltage=voltage, current=current,
            agm_stage_count=len(AGM_STAGES), max_stage_current=MAX_STAGE_CURRENT,
            clamp_voltage=clamp_pb_automatic_target_voltage,
        )
        now = time.time()
        future_profile = data.get("profile", host.PROFILE_CA)
        future_total_start_time = scalars.total_start_time or now
        if (not future_total_start_time or future_total_start_time <= 0
                or (now - future_total_start_time) > SESSION_START_MAX_AGE):
            future_total_start_time = now
        from runtime.charge.session import (
            prepare_trace_identity_application,
            project_trace_identity,
        )
        configuration = getattr(host, "host_configuration", None)
        intent_default = getattr(
            configuration, "restore_trace_default_intent",
            getattr(host, "_v2_intent", "normal"),
        )
        condition_default = getattr(
            configuration, "restore_trace_default_condition",
            getattr(host, "_v2_condition_before", "unknown"),
        )
        preprojected_trace = project_trace_identity(
            data,
            total_start_time=future_total_start_time,
            battery_type=future_profile,
            ah_capacity=scalars.ah_limit,
            battery_id=getattr(host, "_v2_battery_id", None),
            intent_default=intent_default,
            condition_default=condition_default,
            now_s=now,
        )
        prepared_trace_values = prepare_trace_identity_application(
            host, preprojected_trace,
        )

        # Timeline continuation is a pure projection over the accepted
        # document and canonical host constants. Compute it before the first
        # active-session mutation so projection failures remain pre-apply.
        target_finish = scalars.target_finish_time
        target_v_raw = scalars.target_voltage_raw
        target_v = scalars.target_voltage
        target_i = scalars.target_current
        saved_stage_start = scalars.stage_start_time if scalars.stage_start_time is not None else now
        if (not saved_stage_start or saved_stage_start <= 0
                or (now - saved_stage_start) > SESSION_START_MAX_AGE):
            saved_stage_start = now
        timeline = project_restore_stage_timeline(
            current_stage=data.get("stage", host.STAGE_MAIN),
            main_stage=host.STAGE_MAIN,
            mix_stage=host.STAGE_MIX,
            desulfation_stage=host.STAGE_DESULFATION,
            done_stage=host.STAGE_DONE,
            now=now,
            target_finish_time=target_finish,
            saved_stage_start=saved_stage_start,
            existing_finish_timer_start=data.get("finish_timer_start"),
            mix_done_timer=MIX_DONE_TIMER,
        )

        if GUARD_KEY in data:
            host._main_current_guard = restored_guard
            host._main_current_guard_revision = revision

        host._native_recipe_session_selection = selected_native
        host._stage_tracking_enabled = False
        host.battery_type = data.get("profile", host.PROFILE_CA)
        host.ah_capacity = scalars.ah_limit
        host.current_stage = data.get("stage", host.STAGE_MAIN)
        normalize_done_document = False
        if host.current_stage == host.STAGE_DONE:
            if _explicit_storage_outcome(data):
                _set_done_outcome(
                    host,
                    DONE_COMPLETION_STORAGE,
                    DONE_OUTPUT_ON,
                    authoritative=True,
                )
            else:
                _set_done_outcome(
                    host,
                    DONE_COMPLETION_TERMINAL,
                    DONE_OUTPUT_OFF,
                    authoritative=True,
                )
                normalize_done_document = True
        else:
            _set_done_outcome(host, None, DONE_OUTPUT_OFF, authoritative=False)
        host.antisulfate_count = scalars.current_retries
        host._agm_stage_idx = scalars.agm_stage_idx
        host._start_ah = scalars.start_ah
        host._stage_start_ah = scalars.stage_start_ah
        host._stage_start_voltage = scalars.stage_start_voltage
        host._stage_start_current = scalars.stage_start_current
        host._stage_start_temp = scalars.stage_start_temp
        host._safe_wait_next_stage = data.get("safe_wait_next_stage")
        host._safe_wait_target_v = scalars.safe_wait_target_v
        host._safe_wait_target_i = scalars.safe_wait_target_i
        restore_stage_history(
            host, data.get("previous_stage"), data.get("last_transition_reason"),
            data.get("stage_history", []), now=now,
        )
        host._safe_wait_start = scalars.safe_wait_start if scalars.safe_wait_start is not None else now
        if host.current_stage == host.STAGE_SAFE_WAIT:
            allowed_safe_wait_next = {host.STAGE_MAIN, host.STAGE_DONE}
            if host._safe_wait_next_stage not in allowed_safe_wait_next:
                logger.warning(
                    "Restore: invalid safe_wait_next_stage=%r, fallback to %s",
                    host._safe_wait_next_stage,
                    host.STAGE_MAIN,
                )
                host._safe_wait_next_stage = host.STAGE_MAIN
        else:
            host._safe_wait_next_stage = None
        host._first_stage_hold_since = scalars.first_stage_hold_since
        host._first_stage_hold_current = scalars.first_stage_hold_current
        host._stuck_current_since = scalars.stuck_current_since
        host._stuck_current_value = scalars.stuck_current_value

        # v2.6: восстанавливаем общий старт сессии
        host.total_start_time = scalars.total_start_time if scalars.total_start_time is not None else now
        # Валидация total_start_time
        if not host.total_start_time or host.total_start_time <= 0 or (now - host.total_start_time) > SESSION_START_MAX_AGE:
            host.total_start_time = now
            logger.info("Restore: total_start_time invalid or >24h, set to now()")

        from runtime.charge.session import apply_trace_identity
        apply_trace_identity(
            host, preprojected_trace, prepared=prepared_trace_values,
        )

        restored_terminal = False
        if abs(target_v - target_v_raw) >= 0.01:
            logger.warning("Restore: target voltage clamped %.2fV -> %.2fV", target_v_raw, target_v)
        host._restored_target_v = target_v
        host._restored_target_i = target_i
        host.finish_timer_start = data.get("finish_timer_start")
        # Фикс "1970 года": если start_time отсутствует, 0 или старше 24 ч — принудительно now()
        if not saved_stage_start or saved_stage_start <= 0 or (now - saved_stage_start) > SESSION_START_MAX_AGE:
            saved_stage_start = now
            logger.info("Restore: start_time invalid or >24h, set to now()")

        host._session_start_reason = "Auto-restore"

        host.current_stage = timeline.stage
        if timeline.clear_restored_targets:
            host._clear_restored_targets()
        if timeline.stage_start_time is not None:
            host.stage_start_time = timeline.stage_start_time
        if timeline.update_finish_timer_start:
            host.finish_timer_start = timeline.finish_timer_start
        restored_terminal = timeline.restored_terminal
        normalize_done_document = bool(normalize_done_document or restored_terminal)
        remaining_min = timeline.remaining_min

        if target_finish is not None:
            remaining_sec = target_finish - now
            if remaining_sec > 0:
                msg = (
                    f"🔄 <b>Сессия восстановлена!</b>\n\n"
                    f"Продолжаю режим: <code>{host.current_stage}</code>.\n"
                    f"Осталось времени: <code>{remaining_min}</code> мин.\n"
                    f"Цель: <code>{target_v:.1f}</code>В / <code>{target_i:.2f}</code>А"
                )
            else:
                msg = (
                    f"🔄 <b>Сессия восстановлена!</b>\n\n"
                    f"Переход к следующей фазе: <code>{host.current_stage}</code>.\n"
                    f"Цель: <code>{target_v:.1f}</code>В / <code>{target_i:.2f}</code>А"
                )
        else:
            msg = (
                f"🔄 <b>Сессия восстановлена!</b>\n\n"
                f"Продолжаю режим: <code>{host.current_stage}</code>.\n"
                f"Цель: <code>{target_v:.1f}</code>В / <code>{target_i:.2f}</code>А"
            )

        host._reset_delta_and_blanking(now)
        host._temp_comp_last_update_time = 0.0
        host._temp_comp_last_temp = None
        if host.current_stage == host.STAGE_MAIN:
            host._stuck_current_since = scalars.stuck_current_since
            host._stuck_current_value = scalars.stuck_current_value
        if host.current_stage != host.STAGE_MIX:
            host.finish_timer_start = None

        # Синхронизация таймеров с прибором: оцениваем время по накопленным А·ч и току
        i_avg = scalars.measured_average_current
        delta_ah_total = ah - host._start_ah
        delta_ah_stage = ah - host._stage_start_ah
        if delta_ah_total > 0.01 and i_avg > 0.05:
            est_total_h = delta_ah_total / i_avg
            est_total_h = min(est_total_h, SESSION_START_MAX_AGE / 3600)
            host.total_start_time = now - est_total_h * 3600
            logger.info("Restore: total_start_time synced from Ah: %.1f h elapsed", est_total_h)
        if delta_ah_stage > 0.01 and i_avg > 0.05:
            est_stage_h = delta_ah_stage / i_avg
            est_stage_h = min(est_stage_h, SESSION_START_MAX_AGE / 3600)
            host.stage_start_time = now - est_stage_h * 3600
            logger.info("Restore: stage_start_time synced from Ah: %.1f h on stage", est_stage_h)

        elapsed_sec = now - host.stage_start_time
        if elapsed_sec < 0 or elapsed_sec > ELAPSED_MAX_HOURS * 3600:
            host.stage_start_time = now
            logger.warning("Restore: stage_start_time corrected (elapsed invalid)")
        restored_stage_limit = host._get_stage_max_hours()
        restored_target_v, restored_target_i = host._get_target_v_i()
        log_session_header(
            "restore",
            host.current_stage,
            voltage,
            current,
            0.0,
            ah,
            host.battery_type,
            host.ah_capacity,
            host._session_rules_summary(),
            meta={
                "session_reason": host._session_start_reason,
                "stage_limit_h": f"{restored_stage_limit:.1f}" if restored_stage_limit is not None else "—",
                "target_v": f"{restored_target_v:.2f}",
                "target_i": f"{restored_target_i:.2f}",
                "remaining_min": remaining_min,
            },
        )
        finalize_restored_session(
            host,
            data,
            normalize_done_document=normalize_done_document,
            normalize_terminal=_normalize_terminal_done_document,
            session_file=session_file,
            canonical_preimage=raw_bytes,
            restored_terminal=restored_terminal,
            voltage=voltage,
            current=current,
            ah=ah,
        )
        return True, msg

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
