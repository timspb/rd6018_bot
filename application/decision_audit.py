"""Immutable audit trail for the pure V3 decision pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DecisionAuditStep(str, Enum):
    PROGRAM_SELECTION = "PROGRAM_SELECTION"
    PHASE_DECISION = "PHASE_DECISION"
    SAFETY_DECISION = "SAFETY_DECISION"
    INTENT_CREATION = "INTENT_CREATION"
    APPROVAL = "APPROVAL"
    EXECUTION_OUTCOME = "EXECUTION_OUTCOME"


REQUIRED_TRACE_STEPS = tuple(step.value for step in DecisionAuditStep)


@dataclass(frozen=True)
class DecisionAuditEvent:
    event_id: str
    decision_id: str
    intent_id: str
    approval_id: str
    session_id: str
    timestamp: float
    actor: str
    result: str
    step: DecisionAuditStep | str
    reason: str

    def __post_init__(self) -> None:
        for name in (
            "event_id", "decision_id", "session_id", "actor", "result", "reason",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if self.timestamp < 0:
            raise ValueError("audit event timestamp cannot be negative")
        step = self.step if isinstance(self.step, DecisionAuditStep) else DecisionAuditStep(str(self.step))
        object.__setattr__(self, "step", step)


@dataclass(frozen=True)
class DecisionTraceReplay:
    events: tuple[DecisionAuditEvent, ...]
    missing_steps: tuple[str, ...]
    complete: bool

    @property
    def explanations(self) -> tuple[tuple[str, str], ...]:
        return tuple((event.step.value, event.reason) for event in self.events)


@dataclass(frozen=True)
class DecisionAuditTrail:
    """Persistent-value style trail: append returns a new trail."""

    events: tuple[DecisionAuditEvent, ...] = ()

    def append(self, event: DecisionAuditEvent) -> "DecisionAuditTrail":
        if self.events:
            previous = self.events[-1]
            if event.timestamp < previous.timestamp:
                raise ValueError("audit events must be appended in timestamp order")
            if event.decision_id != previous.decision_id:
                raise ValueError("audit trail cannot mix decision identities")
            if event.session_id != previous.session_id:
                raise ValueError("audit trail cannot mix session identities")
            if previous.intent_id and event.intent_id and event.intent_id != previous.intent_id:
                raise ValueError("audit trail cannot mix intent identities")
        if any(existing.event_id == event.event_id for existing in self.events):
            raise ValueError("audit event_id must be unique")
        return DecisionAuditTrail(self.events + (event,))

    def replay(self) -> DecisionTraceReplay:
        seen = {event.step.value for event in self.events}
        missing = tuple(step for step in REQUIRED_TRACE_STEPS if step not in seen)
        return DecisionTraceReplay(self.events, missing, not missing)

    def for_decision(self, decision_id: str) -> "DecisionAuditTrail":
        return DecisionAuditTrail(tuple(event for event in self.events if event.decision_id == decision_id))


__all__ = [
    "DecisionAuditEvent",
    "DecisionAuditStep",
    "DecisionAuditTrail",
    "DecisionTraceReplay",
    "REQUIRED_TRACE_STEPS",
]
