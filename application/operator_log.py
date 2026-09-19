"""Current-session-only operator log presentation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from v3_core.canonical_events import CanonicalChargeEvent, EventType


RELEVANT_EVENTS = frozenset({
    EventType.SESSION_STARTED, EventType.SESSION_PAUSED, EventType.SESSION_RESUMED,
    EventType.SESSION_STOPPED, EventType.SESSION_COMPLETED, EventType.PHASE_STARTED,
    EventType.PHASE_COMPLETED, EventType.PHASE_TRANSITION, EventType.DELTA_STARTED,
    EventType.DELTA_COMPLETED, EventType.HOLD_STARTED, EventType.HOLD_COMPLETED,
    EventType.TERMINATION_DETECTED, EventType.SAFETY_TRIGGERED,
    EventType.CONTAINMENT_REQUESTED, EventType.FAULT_DETECTED,
})


@dataclass(frozen=True)
class OperatorLogEvent:
    timestamp: float
    phase: str
    event: str
    reason: str
    condition: str

    def format(self) -> str:
        stamp = datetime.fromtimestamp(self.timestamp, tz=timezone.utc).strftime("%H:%M:%S")
        return f"{stamp} · {self.phase} · {self.event} · {self.reason}"


@dataclass(frozen=True)
class OperatorLogViewModel:
    session_id: str
    events: tuple[OperatorLogEvent, ...]
    status: str

    @classmethod
    def from_events(
        cls,
        events: tuple[CanonicalChargeEvent, ...],
        *,
        session_id: str,
        trace_id: str | None = None,
    ) -> "OperatorLogViewModel":
        if not session_id or session_id == "UNKNOWN":
            return cls(session_id or "UNKNOWN", (), "AMBIGUOUS_SESSION")
        selected = tuple(
            event for event in events
            if event.session_id == session_id
            and (trace_id is None or event.trace_id == trace_id)
            and event.event_type in RELEVANT_EVENTS
        )
        selected = tuple(sorted(selected, key=lambda item: (item.timestamp, item.event_id)))
        return cls(
            session_id,
            tuple(OperatorLogEvent(
                event.timestamp,
                str(event.phase_after or event.phase_before or "UNKNOWN"),
                event.event_type.value,
                str(event.reason or "UNKNOWN"),
                str(event.metadata.get("condition", "UNKNOWN")),
            ) for event in selected),
            "READY" if selected else "EMPTY_OR_UNKNOWN",
        )

    def format(self) -> str:
        if not self.events:
            return "UNKNOWN · события текущей сессии недоступны"
        return "\n".join(event.format() for event in self.events)


__all__ = ["OperatorLogEvent", "OperatorLogViewModel", "RELEVANT_EVENTS"]
