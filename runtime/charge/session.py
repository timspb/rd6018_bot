"""Pure logical charge session lifecycle."""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass
from enum import Enum

class SessionStatus(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass(frozen=True)
class SessionSnapshot:
    session_id: str | None
    status: SessionStatus
    profile: str | None = None


@dataclass(frozen=True)
class TraceIdentitySnapshot:
    session_id: str
    started_at: float
    battery_id: str | None
    intent: str
    condition_before: str


def new_trace_identity(host: object, *, now: float | None = None) -> TraceIdentitySnapshot:
    """Create a new trace identity from the canonical session lifecycle owner."""
    started_at = float(getattr(host, "total_start_time", 0.0) or now or time.time())
    return TraceIdentitySnapshot(
        session_id=uuid.uuid4().hex,
        started_at=started_at,
        battery_id=getattr(host, "_v2_battery_id", None),
        intent=str(getattr(
            getattr(host, "_v2_intent", "normal"), "value",
            getattr(host, "_v2_intent", "normal"),
        )),
        condition_before=str(getattr(
            getattr(host, "_v2_condition_before", "unknown"), "value",
            getattr(host, "_v2_condition_before", "unknown"),
        )),
    )


def restore_trace_identity(host: object, document: dict[str, object]) -> TraceIdentitySnapshot:
    """Restore identity, including deterministic one-way migration for old sessions."""
    raw_started_at = document.get("v2_trace_started_at")
    if raw_started_at is None:
        raw_started_at = document.get("total_start_time")
    if raw_started_at is None:
        raw_started_at = document.get("saved_at")
    try:
        started_at = float(raw_started_at)
    except (TypeError, ValueError, OverflowError):
        started_at = float(getattr(host, "total_start_time", 0.0) or time.time())
    if not math.isfinite(started_at) or started_at <= 0:
        started_at = float(getattr(host, "total_start_time", 0.0) or time.time())

    raw_id = str(document.get("v2_trace_session_id") or "").strip()
    if not raw_id:
        seed = "|".join((
            str(document.get("profile") or getattr(host, "battery_type", "")),
            str(document.get("ah_limit") or getattr(host, "ah_capacity", "")),
            f"{started_at:.6f}",
            str(document.get("saved_at") or ""),
        ))
        raw_id = uuid.uuid5(uuid.NAMESPACE_URL, f"rd6018-recovery:{seed}").hex

    saved_battery_id = document.get("v2_battery_id")
    configuration = getattr(host, "host_configuration", None)
    intent_default = getattr(
        configuration, "restore_trace_default_intent", getattr(host, "_v2_intent", "normal")
    )
    condition_default = getattr(
        configuration, "restore_trace_default_condition",
        getattr(host, "_v2_condition_before", "unknown"),
    )
    intent_value = str(
        document.get("v2_intent") or getattr(intent_default, "value", intent_default)
    )
    condition_value = str(
        document.get("v2_condition_before")
        or getattr(condition_default, "value", condition_default)
    )
    try:
        intent = type(intent_default)(intent_value)
    except (TypeError, ValueError):
        intent = intent_default
    try:
        condition = type(condition_default)(condition_value)
    except (TypeError, ValueError):
        condition = condition_default
    return TraceIdentitySnapshot(
        session_id=raw_id,
        started_at=started_at,
        battery_id=(
            str(saved_battery_id) if saved_battery_id
            else getattr(host, "_v2_battery_id", None)
        ),
        intent=str(getattr(intent, "value", intent)),
        condition_before=str(getattr(condition, "value", condition)),
    )


def apply_trace_identity(host: object, snapshot: TraceIdentitySnapshot) -> None:
    host._v2_trace_session_id = snapshot.session_id
    host._v2_trace_started_at = snapshot.started_at
    host._v2_battery_id = snapshot.battery_id
    current_intent = getattr(host, "_v2_intent", None)
    current_condition = getattr(host, "_v2_condition_before", None)
    host._v2_intent = (
        type(current_intent)(snapshot.intent)
        if current_intent is not None else snapshot.intent
    )
    host._v2_condition_before = (
        type(current_condition)(snapshot.condition_before)
        if current_condition is not None else snapshot.condition_before
    )


def set_current_stage(host: object, value: str) -> None:
    """Apply a stage value and record its single canonical history edge."""
    previous = getattr(host, "_current_stage", None)
    host._current_stage = value
    if not getattr(host, "_stage_tracking_enabled", False) or previous in (None, value):
        return
    host.previous_stage = previous
    host._stage_history.append({
        "from": previous, "to": value,
        "reason": str(getattr(host, "_last_transition_reason", "") or "").strip(),
        "ts": time.time(),
    })
    host._stage_start_voltage = 0.0
    host._stage_start_current = 0.0
    host._stage_start_temp = 0.0
    host._last_voltage = 0.0
    host._last_current = 0.0
    host._last_temp_ext = 0.0
    host._last_ah = 0.0
    host._last_transition_reason = ""


def restore_stage_history(host: object, previous_stage: object, reason: object, history: object, *, now: float) -> None:
    """Restore the established persisted stage-history schema."""
    host.previous_stage = previous_stage
    host._last_transition_reason = str(reason or "")
    host._stage_history.clear()
    if isinstance(history, list):
        for item in history[-host._stage_history.maxlen:]:
            if not isinstance(item, dict):
                continue
            from_stage = str(item.get("from") or "").strip()
            to_stage = str(item.get("to") or "").strip()
            if not from_stage and not to_stage:
                continue
            try:
                timestamp = float(item.get("ts") or now)
            except (TypeError, ValueError, OverflowError):
                timestamp = float(now)
            host._stage_history.append({
                "from": from_stage, "to": to_stage,
                "reason": str(item.get("reason") or "").strip(), "ts": timestamp,
            })
    if host._stage_history and not host.previous_stage:
        host.previous_stage = str(host._stage_history[-1].get("from") or "") or None


def clear_stage_history(host: object) -> None:
    host.previous_stage = None
    host._last_transition_reason = ""
    host._stage_history.clear()


class SessionManager:
    """Own only logical lifecycle; no persistence or actuator authority."""

    def __init__(self) -> None:
        self._snapshot = SessionSnapshot(None, SessionStatus.IDLE)

    @property
    def snapshot(self) -> SessionSnapshot:
        return self._snapshot

    def start(self, session_id: str, profile: str) -> SessionSnapshot:
        if self._snapshot.status in {SessionStatus.ACTIVE, SessionStatus.PAUSED}:
            raise ValueError("charge session already active")
        if not session_id or not profile:
            raise ValueError("session_id and profile are required")
        self._snapshot = SessionSnapshot(session_id, SessionStatus.ACTIVE, profile)
        return self._snapshot

    def pause(self) -> SessionSnapshot:
        if self._snapshot.status is not SessionStatus.ACTIVE:
            raise ValueError("only an active session can be paused")
        self._snapshot = SessionSnapshot(self._snapshot.session_id, SessionStatus.PAUSED, self._snapshot.profile)
        return self._snapshot

    def resume(self) -> SessionSnapshot:
        if self._snapshot.status is not SessionStatus.PAUSED:
            raise ValueError("only a paused session can be resumed")
        self._snapshot = SessionSnapshot(self._snapshot.session_id, SessionStatus.ACTIVE, self._snapshot.profile)
        return self._snapshot

    def stop(self) -> SessionSnapshot:
        self._snapshot = SessionSnapshot(self._snapshot.session_id, SessionStatus.STOPPED, self._snapshot.profile)
        return self._snapshot
