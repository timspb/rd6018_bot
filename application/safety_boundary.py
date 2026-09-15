"""Pure safety decision boundary; it does not execute containment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class SafetySignalKind(str, Enum):
    TELEMETRY = "telemetry"
    READBACK = "readback"
    WATCHDOG = "watchdog"
    LEASE = "lease"
    MANUAL = "manual"
    TRANSPORT = "transport"


class SafetyDecisionAction(str, Enum):
    ALLOW = "allow"
    OBSERVE = "observe"
    CONTAIN = "contain"


@dataclass(frozen=True)
class SafetySignal:
    kind: SafetySignalKind
    source: str
    healthy: bool
    reason: str


@dataclass(frozen=True)
class SafetyDecision:
    owner: str
    action: SafetyDecisionAction
    signals: tuple[SafetySignal, ...]
    reason: str
    trace_id: str

    def __post_init__(self) -> None:
        if not self.owner.strip() or not self.reason.strip() or not self.trace_id.strip():
            raise ValueError("safety decision identity is required")


@dataclass(frozen=True)
class ContainmentRequest:
    source: str
    trigger: str
    decision_owner: str
    requested_action: str
    trace_id: str
    evidence: Mapping[str, object]

    def __post_init__(self) -> None:
        for value in (self.source, self.trigger, self.decision_owner, self.requested_action, self.trace_id):
            if not value.strip():
                raise ValueError("containment request identity is required")


def decide(signal: SafetySignal, *, trace_id: str, owner: str = "Safety Decision Authority") -> SafetyDecision:
    action = SafetyDecisionAction.ALLOW if signal.healthy else SafetyDecisionAction.CONTAIN
    return SafetyDecision(owner, action, (signal,), signal.reason, trace_id)


def containment_request(decision: SafetyDecision, *, requested_action: str = "verified_output_off") -> ContainmentRequest:
    if decision.action is not SafetyDecisionAction.CONTAIN:
        raise ValueError("containment requires a CONTAIN decision")
    return ContainmentRequest(
        source=decision.owner,
        trigger=decision.reason,
        decision_owner=decision.owner,
        requested_action=requested_action,
        trace_id=decision.trace_id,
        evidence={"signals": tuple(signal.kind.value for signal in decision.signals)},
    )


__all__ = ["SafetySignalKind", "SafetyDecisionAction", "SafetySignal", "SafetyDecision", "ContainmentRequest", "decide", "containment_request"]
