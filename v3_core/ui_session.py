"""Pure V3 session timeline and presentation contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4


class SessionState(str, Enum):
    UNKNOWN = "UNKNOWN"
    WAITING = "WAITING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TimelineEventType(str, Enum):
    SESSION_STARTED = "SESSION_STARTED"
    PHASE_CHANGED = "PHASE_CHANGED"
    DELTA_STARTED = "DELTA_STARTED"
    DELTA_COMPLETED = "DELTA_COMPLETED"
    HOLD_STARTED = "HOLD_STARTED"
    HOLD_COMPLETED = "HOLD_COMPLETED"
    CHARGE_COMPLETED = "CHARGE_COMPLETED"
    SESSION_STOPPED = "SESSION_STOPPED"
    FAULT_EVENT = "FAULT_EVENT"


@dataclass(frozen=True)
class SessionViewModel:
    session_id: str
    started_at: datetime
    current_phase: str
    elapsed_time_s: float
    current_state: SessionState

    def __post_init__(self) -> None:
        if not self.session_id.strip() or not self.current_phase.strip():
            raise ValueError("session identity and phase are required")
        if self.elapsed_time_s < 0:
            raise ValueError("elapsed time cannot be negative")


@dataclass(frozen=True)
class ChargeTimelineEvent:
    session_id: str
    event_type: TimelineEventType
    timestamp: datetime
    sequence: int
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.session_id.strip() or self.sequence < 0:
            raise ValueError("timeline identity is invalid")


@dataclass(frozen=True)
class TimelineDisplayEvent:
    """Operator-safe representation of one current-session timeline event."""

    event_type: TimelineEventType | None
    event_time: str
    phase: str
    reason: str
    condition: str


@dataclass(frozen=True)
class TimelineDisplay:
    """Display result that distinguishes an empty timeline from empty text."""

    status: str
    events: tuple[TimelineDisplayEvent, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"READY", "UNKNOWN"}:
            raise ValueError("unsupported timeline display status")


@dataclass(frozen=True)
class GraphSample:
    offset_s: float
    voltage: float | None
    current: float | None
    power: float | None
    temperature: float | None


@dataclass(frozen=True)
class SessionGraphBuffer:
    session_id: str
    samples: tuple[GraphSample, ...] = ()
    markers: tuple[ChargeTimelineEvent, ...] = ()

    def append(self, sample: GraphSample) -> "SessionGraphBuffer":
        if sample.offset_s < 0:
            raise ValueError("graph offset cannot be negative")
        return SessionGraphBuffer(self.session_id, self.samples + (sample,), self.markers)

    def mark(self, event: ChargeTimelineEvent) -> "SessionGraphBuffer":
        if event.session_id != self.session_id:
            raise ValueError("graph marker belongs to another session")
        return SessionGraphBuffer(self.session_id, self.samples, self.markers + (event,))


@dataclass(frozen=True)
class CurrentChargeSnapshot:
    session: SessionViewModel
    profile: str
    phase: str
    strategy: str
    voltage: float | None
    current: float | None
    power: float | None
    temperature: float | None
    last_transitions: tuple[ChargeTimelineEvent, ...]
    safety_status: str


class SessionTimeline:
    """Owns presentation history for one session only."""

    def __init__(self) -> None:
        self.session: SessionViewModel | None = None
        self.events: tuple[ChargeTimelineEvent, ...] = ()
        self.graph: SessionGraphBuffer | None = None

    def start(self, *, started_at: datetime, phase: str = "MAIN") -> SessionViewModel:
        session = SessionViewModel(uuid4().hex, started_at, phase, 0.0, SessionState.ACTIVE)
        self.session = session
        self.events = (ChargeTimelineEvent(session.session_id, TimelineEventType.SESSION_STARTED, started_at, 0, {"phase": phase}),)
        self.graph = SessionGraphBuffer(session.session_id)
        return session

    def add(self, event_type: TimelineEventType, *, timestamp: datetime, payload: Mapping[str, Any] | None = None) -> ChargeTimelineEvent:
        if self.session is None:
            raise ValueError("session is not active")
        event = ChargeTimelineEvent(self.session.session_id, event_type, timestamp, len(self.events), dict(payload or {}))
        self.events += (event,)
        if self.graph is not None and event_type in {TimelineEventType.PHASE_CHANGED, TimelineEventType.DELTA_STARTED, TimelineEventType.DELTA_COMPLETED, TimelineEventType.HOLD_STARTED, TimelineEventType.HOLD_COMPLETED, TimelineEventType.FAULT_EVENT}:
            self.graph = self.graph.mark(event)
        return event

    def stop(self, *, timestamp: datetime, failed: bool = False) -> ChargeTimelineEvent:
        if self.session is None:
            raise ValueError("session is not active")
        event_type = TimelineEventType.FAULT_EVENT if failed else TimelineEventType.SESSION_STOPPED
        event = self.add(event_type, timestamp=timestamp, payload={"state": SessionState.FAILED.value if failed else SessionState.COMPLETED.value})
        self.session = SessionViewModel(self.session.session_id, self.session.started_at, self.session.current_phase, max(0.0, (timestamp - self.session.started_at).total_seconds()), SessionState.FAILED if failed else SessionState.COMPLETED)
        return event


class OperatorTimelineFormatter:
    """Expose only operator events; telemetry ticks/FSM loops are omitted."""

    _allowed = frozenset(TimelineEventType)

    def format(self, events: tuple[ChargeTimelineEvent, ...] | list[ChargeTimelineEvent]) -> tuple[ChargeTimelineEvent, ...]:
        ordered = sorted(events, key=lambda event: (event.timestamp, event.sequence))
        return tuple(event for event in ordered if event.event_type in self._allowed)

    def display(self, events: tuple[ChargeTimelineEvent, ...] | list[ChargeTimelineEvent], *, session_id: str | None = None) -> TimelineDisplay:
        """Build a current-session display without inventing lifecycle events."""

        current = tuple(event for event in self.format(events) if session_id is None or event.session_id == session_id)
        if not current:
            return TimelineDisplay("UNKNOWN")
        return TimelineDisplay("READY", tuple(self._display_event(event) for event in current))

    @staticmethod
    def _display_event(event: ChargeTimelineEvent) -> TimelineDisplayEvent:
        payload = dict(event.payload)
        phase = str(payload.get("phase") or payload.get("to") or payload.get("phase_after") or "UNKNOWN")
        reason = payload.get("reason")
        condition = payload.get("condition") or payload.get("waiting") or payload.get("unmet_condition")
        defaults = {
            TimelineEventType.DELTA_COMPLETED: "Delta complete",
            TimelineEventType.HOLD_COMPLETED: "Hold complete",
            TimelineEventType.CHARGE_COMPLETED: "Termination detected",
        }
        reason = str(reason or defaults.get(event.event_type) or "UNKNOWN")
        condition = str(condition or "UNKNOWN")
        return TimelineDisplayEvent(event.event_type, event.timestamp.isoformat(), phase, reason, condition)


__all__ = [
    "SessionState", "TimelineEventType", "SessionViewModel", "ChargeTimelineEvent",
    "GraphSample", "SessionGraphBuffer", "CurrentChargeSnapshot", "SessionTimeline",
    "TimelineDisplayEvent", "TimelineDisplay", "OperatorTimelineFormatter",
]
