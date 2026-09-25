"""Shadow-only containment outcome collection.

The collector consumes path identifiers and creates immutable records. It has
no persistence, runtime callback, HA, lease, controller, or physical adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

from .containment_mapping import known_containment_mappings
from .containment_result import ContainmentVerificationState


@dataclass(frozen=True)
class ContainmentObservationRecord:
    event_id: str
    trace_id: str
    source: str
    trigger: str
    requested_action: str
    verification_state: ContainmentVerificationState
    timestamp: float
    session_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "event_id",
            "trace_id",
            "source",
            "trigger",
            "requested_action",
            "session_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required")
        if not isinstance(self.verification_state, ContainmentVerificationState):
            object.__setattr__(
                self,
                "verification_state",
                ContainmentVerificationState(self.verification_state),
            )
        if not isinstance(self.timestamp, (int, float)) or not isfinite(float(self.timestamp)):
            raise ValueError("timestamp must be finite")


class ContainmentObservationCollector:
    """Create shadow records without executing or persisting anything."""

    def __init__(self) -> None:
        self._mappings = {item.path_id: item for item in known_containment_mappings()}

    def observe(
        self,
        path_id: str,
        *,
        trace_id: str,
        session_id: str,
        event_id: str | None = None,
        timestamp: float | None = None,
    ) -> ContainmentObservationRecord:
        mapping = self._mappings.get(path_id)
        now = datetime.now(timezone.utc).timestamp() if timestamp is None else timestamp
        if mapping is None:
            return ContainmentObservationRecord(
                event_id=event_id or f"observation:unknown:{path_id}",
                trace_id=trace_id,
                source="unknown",
                trigger=path_id,
                requested_action="unknown",
                verification_state=ContainmentVerificationState.UNKNOWN,
                timestamp=now,
                session_id=session_id,
            )
        return ContainmentObservationRecord(
            event_id=event_id or f"observation:{mapping.path_id}",
            trace_id=trace_id,
            source=mapping.source,
            trigger=mapping.trigger,
            requested_action=mapping.requested_action,
            verification_state=mapping.verification_state,
            timestamp=now,
            session_id=session_id,
        )

