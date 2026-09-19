"""Validation of the minimum V3 shadow evidence chain; read/replay only."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from v3_core.canonical_events import CanonicalChargeEvent, EventType


class EvidenceGap(str, Enum):
    MISSING_EVENT = "MISSING_EVENT"
    MISSING_SOURCE = "MISSING_SOURCE"
    STALE_DATA = "STALE_DATA"
    TIMELINE_CONFLICT = "TIMELINE_CONFLICT"
    UNKNOWN = "UNKNOWN"


REQUIRED_CHAIN: tuple[EventType, ...] = (
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


@dataclass(frozen=True)
class EvidenceChainGap:
    category: EvidenceGap
    event_type: str
    source: str
    owner: str
    resolution: str


@dataclass(frozen=True)
class EvidenceChainResult:
    complete: bool
    ordered_event_types: tuple[str, ...]
    gaps: tuple[EvidenceChainGap, ...]
    replay_safe: bool


class ShadowEvidenceChainValidator:
    """Validates supplied events and never reads or mutates live systems."""

    def validate(self, events: Iterable[CanonicalChargeEvent], *, session_id: str, max_age_s: float | None = None, now: float | None = None) -> EvidenceChainResult:
        supplied = tuple(events)
        gaps: list[EvidenceChainGap] = []
        if not supplied:
            return EvidenceChainResult(False, (), (EvidenceChainGap(EvidenceGap.MISSING_EVENT, "chain", "no evidence", "V3 observability", "collect a V2-owned read-only session"),), False)
        if any(event.session_id != session_id for event in supplied):
            gaps.append(EvidenceChainGap(EvidenceGap.TIMELINE_CONFLICT, "session", "canonical events", "V3 observability", "isolate events by session_id"))
        if any(event.timestamp <= 0 or not event.trace_id or not event.session_id for event in supplied):
            gaps.append(EvidenceChainGap(EvidenceGap.MISSING_SOURCE, "identity", "canonical events", "V3 observability", "attach timestamp, session_id and trace_id"))
        if any(not event.metadata.get("telemetry_ref") for event in supplied):
            gaps.append(EvidenceChainGap(EvidenceGap.MISSING_SOURCE, "telemetry correlation", "telemetry collector", "V3 observability", "attach telemetry_ref to every canonical event"))
        ordered = tuple(sorted((event for event in supplied if event.session_id == session_id), key=lambda item: (item.timestamp, item.event_id)))
        if any(right.timestamp < left.timestamp for left, right in zip(ordered, ordered[1:])):
            gaps.append(EvidenceChainGap(EvidenceGap.TIMELINE_CONFLICT, "ordering", "canonical timeline", "V3 observability", "normalize and reject out-of-order events"))
        if max_age_s is not None and now is not None and any(now - event.timestamp > max_age_s for event in ordered):
            gaps.append(EvidenceChainGap(EvidenceGap.STALE_DATA, "chain", "canonical events", "V3 observability", "collect a fresh observation window"))
        present = {event.event_type for event in ordered}
        for required in REQUIRED_CHAIN:
            if required not in present:
                gaps.append(EvidenceChainGap(EvidenceGap.MISSING_EVENT, required.value, "V2 journal/history", "V2 production owner", "emit or capture the event without changing ownership"))
        positions = [next((index for index, event in enumerate(ordered) if event.event_type is required), None) for required in REQUIRED_CHAIN]
        if any(index is None for index in positions):
            pass
        elif positions != sorted(positions):
            gaps.append(EvidenceChainGap(EvidenceGap.TIMELINE_CONFLICT, "required chain", "canonical timeline", "V3 observability", "reconcile source ordering before replay"))
        complete = not gaps
        return EvidenceChainResult(complete, tuple(event.event_type.value for event in ordered), tuple(gaps), complete)


__all__ = ["EvidenceGap", "REQUIRED_CHAIN", "EvidenceChainGap", "EvidenceChainResult", "ShadowEvidenceChainValidator"]
