"""Observer-only session identity and timeline correlation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from v3_core.canonical_events import CanonicalChargeEvent, EventType


class TimelineStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    AMBIGUOUS = "AMBIGUOUS"


class EventBucket(str, Enum):
    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class SessionIdentityModel:
    session_id: str
    created_at: float
    source: str
    profile: str | None
    initial_phase: str | None
    restored: bool = False
    resumed: bool = False

    @classmethod
    def create(cls, *, session_id: str, created_at: float, source: str, profile: str | None, initial_phase: str | None, restored: bool = False, resumed: bool = False) -> "SessionIdentityModel":
        if not session_id or created_at <= 0 or not source:
            raise ValueError("session identity requires id, positive timestamp and source")
        if restored and resumed:
            raise ValueError("session cannot be both restored and resumed")
        return cls(session_id, created_at, source, profile, initial_phase, restored, resumed)


@dataclass(frozen=True)
class CorrelatedEvent:
    event: CanonicalChargeEvent
    bucket: EventBucket
    reason: str


@dataclass(frozen=True)
class TimelineReconstructionResult:
    status: TimelineStatus
    session: SessionIdentityModel
    current_events: tuple[CanonicalChargeEvent, ...]
    historical_events: tuple[CanonicalChargeEvent, ...]
    ambiguous_events: tuple[CanonicalChargeEvent, ...]
    missing_event_types: tuple[str, ...]


@dataclass(frozen=True)
class CurrentSessionTimeline:
    session_id: str
    events: tuple[CanonicalChargeEvent, ...]
    graph_reset: bool = True
    historical_events_included: bool = False


REQUIRED_TIMELINE = (
    EventType.SESSION_STARTED,
    EventType.PHASE_STARTED,
    EventType.PHASE_TRANSITION,
    EventType.DELTA_STARTED,
    EventType.DELTA_COMPLETED,
    EventType.HOLD_STARTED,
    EventType.HOLD_COMPLETED,
    EventType.TERMINATION_DETECTED,
    EventType.SESSION_STOPPED,
)


class EventCorrelationResolver:
    """Correlates supplied events without guessing through conflicts."""

    def classify(self, event: CanonicalChargeEvent, session: SessionIdentityModel, *, current_phase: str | None = None, telemetry_timestamps: tuple[float, ...] = ()) -> CorrelatedEvent:
        if not event.session_id or not event.trace_id:
            return CorrelatedEvent(event, EventBucket.AMBIGUOUS, "missing session or trace identity")
        if event.session_id != session.session_id:
            if event.timestamp >= session.created_at and (not telemetry_timestamps or min(abs(event.timestamp - value) for value in telemetry_timestamps) <= 300):
                return CorrelatedEvent(event, EventBucket.AMBIGUOUS, "conflicting session identity in current time range")
            return CorrelatedEvent(event, EventBucket.HISTORICAL, "different session identity")
        if event.timestamp < session.created_at:
            return CorrelatedEvent(event, EventBucket.HISTORICAL, "event predates session identity")
        if current_phase and event.phase_after and event.event_type is EventType.PHASE_TRANSITION and event.phase_after != current_phase:
            return CorrelatedEvent(event, EventBucket.AMBIGUOUS, "phase conflicts with current observation")
        return CorrelatedEvent(event, EventBucket.CURRENT, "session, time and phase agree")

    def resolve(self, events: Iterable[CanonicalChargeEvent], session: SessionIdentityModel, *, current_phase: str | None = None, telemetry_timestamps: tuple[float, ...] = ()) -> tuple[CorrelatedEvent, ...]:
        return tuple(self.classify(event, session, current_phase=current_phase, telemetry_timestamps=telemetry_timestamps) for event in events)


class TimelineReconstructor:
    def __init__(self, resolver: EventCorrelationResolver | None = None) -> None:
        self._resolver = resolver or EventCorrelationResolver()

    def rebuild(self, events: Iterable[CanonicalChargeEvent], session: SessionIdentityModel, *, current_phase: str | None = None, telemetry_timestamps: tuple[float, ...] = ()) -> TimelineReconstructionResult:
        correlated = self._resolver.resolve(events, session, current_phase=current_phase, telemetry_timestamps=telemetry_timestamps)
        current = tuple(item.event for item in correlated if item.bucket is EventBucket.CURRENT)
        historical = tuple(item.event for item in correlated if item.bucket is EventBucket.HISTORICAL)
        ambiguous = tuple(item.event for item in correlated if item.bucket is EventBucket.AMBIGUOUS)
        present = {event.event_type for event in current}
        missing = tuple(item.value for item in REQUIRED_TIMELINE if item not in present)
        ordered = tuple(sorted(current, key=lambda item: (item.timestamp, item.event_id)))
        positions = [next((index for index, event in enumerate(ordered) if event.event_type is required), None) for required in REQUIRED_TIMELINE]
        if ambiguous or any(index is None for index in positions) and not current:
            status = TimelineStatus.AMBIGUOUS if ambiguous else TimelineStatus.PARTIAL
        elif ambiguous or any(index is None for index in positions) or positions != sorted(positions):
            status = TimelineStatus.AMBIGUOUS if ambiguous or (positions != sorted(positions) if all(index is not None for index in positions) else False) else TimelineStatus.PARTIAL
        else:
            status = TimelineStatus.COMPLETE
        return TimelineReconstructionResult(status, session, ordered, historical, ambiguous, missing)


class CurrentSessionTimelineProvider:
    def build(self, result: TimelineReconstructionResult) -> CurrentSessionTimeline:
        if result.status is TimelineStatus.AMBIGUOUS:
            raise ValueError("ambiguous timeline cannot be presented as current")
        return CurrentSessionTimeline(result.session.session_id, result.current_events, graph_reset=True, historical_events_included=False)


__all__ = ["TimelineStatus", "EventBucket", "SessionIdentityModel", "CorrelatedEvent", "TimelineReconstructionResult", "CurrentSessionTimeline", "EventCorrelationResolver", "TimelineReconstructor", "CurrentSessionTimelineProvider"]
