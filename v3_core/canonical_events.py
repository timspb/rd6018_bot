"""Canonical charge-event taxonomy and timeline normalization contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class EventType(str, Enum):
    SESSION_STARTED = "SessionStarted"
    SESSION_PAUSED = "SessionPaused"
    SESSION_RESUMED = "SessionResumed"
    SESSION_STOPPED = "SessionStopped"
    SESSION_COMPLETED = "SessionCompleted"
    PHASE_STARTED = "PhaseStarted"
    PHASE_COMPLETED = "PhaseCompleted"
    PHASE_TRANSITION = "PhaseTransition"
    DELTA_STARTED = "DeltaStarted"
    DELTA_COMPLETED = "DeltaCompleted"
    HOLD_STARTED = "HoldStarted"
    HOLD_COMPLETED = "HoldCompleted"
    TERMINATION_DETECTED = "TerminationDetected"
    MANUAL_OVERRIDE_STARTED = "ManualOverrideStarted"
    MANUAL_OVERRIDE_COMPLETED = "ManualOverrideCompleted"
    CONTROL_TRANSFERRED = "ControlTransferred"
    PROFILE_CHANGED = "ProfileChanged"
    SAFETY_TRIGGERED = "SafetyTriggered"
    CONTAINMENT_REQUESTED = "ContainmentRequested"
    FAULT_DETECTED = "FaultDetected"
    FAULT_RESOLVED = "FaultResolved"
    RESTART_DETECTED = "RestartDetected"
    STATE_RECOVERED = "StateRecovered"
    STATE_REVALIDATED = "StateRevalidated"


class SessionStopReason(str, Enum):
    OPERATOR_STOP = "operator_stop"
    MAIN_HOLD_COMPLETE = "main_hold_complete"
    TERMINATION = "termination"
    SAFETY = "safety"
    UNKNOWN = "unknown"


class PhaseTransitionReason(str, Enum):
    MAIN_TO_MIX = "main_to_mix"
    COOLING_RESUME = "cooling_resume"
    OPERATOR = "operator"
    STRATEGY = "strategy"
    RECOVERY = "recovery"
    UNKNOWN = "unknown"


class ControlReason(str, Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    OPERATOR = "operator"
    UNKNOWN = "unknown"


class SafetyReason(str, Enum):
    WATCHDOG = "watchdog"
    TELEMETRY_UNAVAILABLE = "telemetry_unavailable"
    TRANSPORT_UNAVAILABLE = "transport_unavailable"
    LEASE = "lease"
    UNKNOWN = "unknown"


class MigrationReason(str, Enum):
    RESTART = "restart"
    RESTORE = "restore"
    REVALIDATION = "revalidation"
    UNKNOWN = "unknown"


class EventSource(str, Enum):
    DOMAIN = "domain"
    JOURNAL = "journal"
    LEGACY_HISTORY = "legacy history"
    TELEMETRY = "telemetry"
    MANUAL = "manual"
    SAFETY = "safety"


class EventActivity(str, Enum):
    ACTIVE = "ACTIVE"
    HISTORICAL = "HISTORICAL"
    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CanonicalChargeEvent:
    event_id: str
    timestamp: float
    session_id: str
    trace_id: str
    source: EventSource
    event_type: EventType
    phase_before: str | None = None
    phase_after: str | None = None
    profile: str | None = None
    reason: str | None = None
    severity: str = "INFO"
    activity: EventActivity = EventActivity.ACTIVE
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalTimelineSnapshot:
    session_id: str
    current_phase: str | None
    current_state: str
    ordered_events: tuple[CanonicalChargeEvent, ...]
    active_alerts: tuple[str, ...] = ()


class EventNormalizer:
    """Normalizes supplied source records; it does not read source systems."""

    def normalize(self, raw: Mapping[str, Any], *, source: EventSource, session_id: str, trace_id: str, event_id: str) -> CanonicalChargeEvent:
        raw_type = str(raw.get("event_type", raw.get("event", ""))).upper()
        before = raw.get("phase_before", raw.get("old"))
        after = raw.get("phase_after", raw.get("new"))
        reason = str(raw.get("reason", "")) or None
        event_type = self._event_type(raw_type, before, after, reason)
        activity = EventActivity.HISTORICAL if bool(raw.get("historical", False)) else EventActivity.ACTIVE
        if raw_type.startswith("EMERGENCY_UNAVAILABLE") and not raw.get("confirmed", False):
            activity = EventActivity.HISTORICAL
        if raw.get("resolved", False):
            activity = EventActivity.RESOLVED
        return CanonicalChargeEvent(event_id, float(raw.get("timestamp", 0.0)), session_id, trace_id, source, event_type, str(before) if before is not None else None, str(after) if after is not None else None, raw.get("profile"), reason, str(raw.get("severity", "INFO")), activity, dict(raw.get("metadata", {})))

    @staticmethod
    def _event_type(raw_type: str, before: Any, after: Any, reason: str | None) -> EventType:
        if raw_type in {"SESSION_START", "START", "SESSION_STARTED"}:
            return EventType.SESSION_STARTED
        if raw_type in {"STOP", "SESSION_STOP", "SESSION_STOPPED"}:
            return EventType.SESSION_STOPPED
        if raw_type in {"HOLD_START", "HOLD_STARTED"}:
            return EventType.HOLD_STARTED
        if raw_type in {"HOLD_END", "HOLD_COMPLETED"}:
            return EventType.HOLD_COMPLETED
        if raw_type in {"DELTA_START", "DELTA_STARTED"}:
            return EventType.DELTA_STARTED
        if raw_type in {"DELTA_END", "DELTA_COMPLETED"}:
            return EventType.DELTA_COMPLETED
        if raw_type.startswith("MANUAL_TRANSITION") or before is not None or after is not None:
            return EventType.PHASE_TRANSITION
        if raw_type.startswith("EMERGENCY") or raw_type.startswith("FAULT"):
            return EventType.FAULT_DETECTED
        if raw_type.startswith("CONTAINMENT"):
            return EventType.CONTAINMENT_REQUESTED
        return EventType.PHASE_STARTED


def build_timeline(events: tuple[CanonicalChargeEvent, ...], *, session_id: str, current_phase: str | None, current_state: str, active_alerts: tuple[str, ...] = ()) -> CanonicalTimelineSnapshot:
    ordered = tuple(sorted((event for event in events if event.session_id == session_id), key=lambda item: (item.timestamp, item.event_id)))
    return CanonicalTimelineSnapshot(session_id, current_phase, current_state, ordered, active_alerts)


__all__ = ["EventType", "SessionStopReason", "PhaseTransitionReason", "ControlReason", "SafetyReason", "MigrationReason", "EventSource", "EventActivity", "CanonicalChargeEvent", "CanonicalTimelineSnapshot", "EventNormalizer", "build_timeline"]
