"""Dry-run adapter from ActuatorIntent to a V2 execution request.

The adapter validates and translates data only. It deliberately does not call
the V2 owner, SafeOutputCoordinator, HA, ESPHome, controller, or FSM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .actuator_intent import (
    ActuatorIntent,
    ActuatorOperation,
    ActuatorTrigger,
    PhysicalVerificationExpectation,
    RollbackPolicy,
    SafetyContext,
)


@dataclass(frozen=True)
class V2ActuatorExecutionRequest:
    """Transport-free request for the existing V2 owner."""

    trace_id: str
    source: str
    operation: ActuatorOperation
    target: Any
    reason: str
    owner: str
    trigger: ActuatorTrigger
    rollback_policy: RollbackPolicy
    safety_context: SafetyContext
    verification_expectation: PhysicalVerificationExpectation

    def __post_init__(self) -> None:
        if not self.trace_id.strip() or not self.source.strip() or not self.reason.strip() or not self.owner.strip():
            raise ValueError("V2 execution request identity fields are required")
        if not isinstance(self.operation, ActuatorOperation):
            raise ValueError("invalid actuator operation")
        if not isinstance(self.trigger, ActuatorTrigger):
            raise ValueError("invalid actuator trigger")
        if not isinstance(self.rollback_policy, RollbackPolicy):
            raise ValueError("invalid rollback policy")
        if not isinstance(self.safety_context, SafetyContext):
            raise TypeError("typed SafetyContext is required")
        if not isinstance(self.verification_expectation, PhysicalVerificationExpectation):
            raise TypeError("typed PhysicalVerificationExpectation is required")


class ActuatorIntentAdapter:
    """Validate/map an intent without handing it to an execution owner."""

    _ALLOWED_OWNERS = {
        ActuatorOperation.OUTPUT_ON: frozenset({
            "V2 runtime safety surface",
            "Manual manager + SafeOutput path",
            "V2 transaction owner",
        }),
        ActuatorOperation.OUTPUT_OFF: frozenset({
            "V2 watchdog + safety",
            "Manual manager + safety",
            "Manual runtime safety",
            "SafeOutputCoordinator",
        }),
        ActuatorOperation.SET_VOLTAGE: frozenset({
            "V2 runtime safety surface",
            "diagnostic safety boundary",
        }),
        ActuatorOperation.SET_CURRENT: frozenset({
            "V2 runtime safety surface",
            "diagnostic safety boundary",
        }),
    }

    _BLOCKED_SOURCES = frozenset({"telegram", "ui", "direct_physical", "unknown"})

    def adapt(self, intent: ActuatorIntent) -> V2ActuatorExecutionRequest:
        if not isinstance(intent, ActuatorIntent):
            raise TypeError("ActuatorIntent is required")
        if intent.source.strip().lower() in self._BLOCKED_SOURCES:
            raise ValueError("actuator intent source is not an execution authority")
        allowed = self._ALLOWED_OWNERS.get(intent.requested_operation, frozenset())
        if intent.owner not in allowed:
            raise ValueError(
                f"owner {intent.owner!r} is not allowed for {intent.requested_operation.value}"
            )
        if intent.safety_context.containment_state == "blocked":
            raise ValueError("actuator intent is blocked by safety context")
        return V2ActuatorExecutionRequest(
            trace_id=intent.trace_id,
            source=intent.source,
            operation=intent.requested_operation,
            target=intent.target,
            reason=intent.reason,
            owner=intent.owner,
            trigger=intent.trigger,
            rollback_policy=intent.rollback_policy,
            safety_context=intent.safety_context,
            verification_expectation=intent.verification_expectation,
        )
