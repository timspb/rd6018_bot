"""Canonical charge-session document candidate projection."""

from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any, Optional, Tuple

from runtime.charge.start_pending import SESSION_FILE, read_start_pending
from runtime.charge.terminal_intent import (
    DONE_COMPLETION_STORAGE,
    DONE_COMPLETION_TERMINAL,
    DONE_OUTPUT_ON,
    DONE_OUTPUT_OFF,
    TerminalPersistenceRequest,
)
from runtime.charge.restore_admission import DONE_STATE_VERSION

logger = logging.getLogger("rd6018")


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
