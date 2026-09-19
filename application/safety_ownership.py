"""Read-only safety ownership coordinator.

This module records detection -> decision -> containment without dispatching
anything.  Existing V2, watchdog and ESPHome safety writers remain active;
this is an observation/contract boundary only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .safety_boundary import (
    SAFETY_DECISION_OWNER,
    SAFETY_OWNERSHIP_INVENTORY,
    ContainmentRequest,
    SafetyDecision,
    SafetyDecisionAction,
    SafetySignal,
    SafetySignalKind,
    decide,
    containment_request,
)


@dataclass(frozen=True)
class SafetyObservation:
    signal: SafetySignal
    decision: SafetyDecision
    containment: Optional[ContainmentRequest]
    dispatch_enabled: bool = False


class SafetyOwnershipCoordinator:
    """Canonical logical decision owner, with no physical side effects."""

    owner = SAFETY_DECISION_OWNER

    def __init__(self) -> None:
        self._history: list[SafetyObservation] = []

    def evaluate(self, signal: SafetySignal, *, trace_id: str) -> SafetyObservation:
        decision = decide(signal, trace_id=trace_id, owner=self.owner)
        request = containment_request(decision) if decision.action is SafetyDecisionAction.CONTAIN else None
        observation = SafetyObservation(signal, decision, request)
        self._history.append(observation)
        return observation

    def history(self) -> tuple[SafetyObservation, ...]:
        return tuple(self._history)

    @staticmethod
    def ownership_conflicts() -> tuple[str, ...]:
        owners = {entry.decision_owner for entry in SAFETY_OWNERSHIP_INVENTORY}
        return tuple(sorted(owner for owner in owners if owner != SAFETY_DECISION_OWNER))

    @staticmethod
    def physical_dispatch_enabled() -> bool:
        return False


__all__ = ["SafetyObservation", "SafetyOwnershipCoordinator"]
