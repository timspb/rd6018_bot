"""Canonical, session-isolated operator timeline integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from v3_core.canonical_events import CanonicalChargeEvent, CanonicalTimelineSnapshot

from .charge_lifecycle import ChargeLifecycleSnapshot


@dataclass(frozen=True)
class OperatorTimelineEvent:
    timestamp: float
    phase: str
    reason: str
    condition: str
    event_type: str
    trace_id: str


@dataclass(frozen=True)
class CanonicalOperatorTimeline:
    session_id: str
    events: tuple[OperatorTimelineEvent, ...]
    graph_session_id: str
    status: str

    @classmethod
    def from_sources(
        cls,
        lifecycle: ChargeLifecycleSnapshot,
        events: Iterable[CanonicalChargeEvent],
        canonical_snapshot: CanonicalTimelineSnapshot | None = None,
    ) -> "CanonicalOperatorTimeline":
        if canonical_snapshot is not None and canonical_snapshot.session_id != lifecycle.session_id:
            return cls(lifecycle.session_id, (), lifecycle.session_id, "UNKNOWN")
        current = tuple(event for event in events if event.session_id == lifecycle.session_id and event.trace_id == lifecycle.trace_id)
        current = tuple(sorted(current, key=lambda event: (event.timestamp, event.event_id)))
        display = tuple(
            OperatorTimelineEvent(
                event.timestamp,
                str(event.phase_after or event.phase_before or lifecycle.current_phase),
                str(event.reason or "UNKNOWN"),
                str(event.metadata.get("condition") or event.metadata.get("waiting") or "UNKNOWN"),
                event.event_type.value,
                event.trace_id,
            )
            for event in current
        )
        return cls(lifecycle.session_id, display, lifecycle.session_id, "READY" if display else "UNKNOWN")


__all__ = ["CanonicalOperatorTimeline", "OperatorTimelineEvent"]
