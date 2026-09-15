"""Data-only actuator intent and shadow mapping contract.

This module does not execute an intent and deliberately has no HA, ESPHome,
controller, safety or physical-layer imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4


class ActuatorOperation(str, Enum):
    OUTPUT_ON = "output_on"
    OUTPUT_OFF = "output_off"
    SET_VOLTAGE = "set_voltage"
    SET_CURRENT = "set_current"


class ActuatorTrigger(str, Enum):
    START_REQUEST = "start_request"
    STOP_REQUEST = "stop_request"
    SAFETY_CONTAINMENT = "safety_containment"
    MANUAL_ACTION = "manual_action"
    RECOVERY = "recovery"
    WATCHDOG = "watchdog"
    LEASE_EXPIRY = "lease_expiry"


class RollbackPolicy(str, Enum):
    NONE = "none"
    SAFE_OFF = "safe_off"
    RESTORE_PREVIOUS = "restore_previous"
    CONTAIN_AND_LATCH = "contain_and_latch"


@dataclass(frozen=True)
class SafetyContext:
    telemetry_state: str
    lease_state: str
    containment_state: str
    verification_state: str
    limits_reference: str

    def __post_init__(self) -> None:
        for field_name in (
            "telemetry_state",
            "lease_state",
            "containment_state",
            "verification_state",
            "limits_reference",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required")

    def to_dict(self) -> dict[str, str]:
        return {
            "telemetry_state": self.telemetry_state,
            "lease_state": self.lease_state,
            "containment_state": self.containment_state,
            "verification_state": self.verification_state,
            "limits_reference": self.limits_reference,
        }


@dataclass(frozen=True)
class PhysicalVerificationExpectation:
    expected_state: str
    verification_required: bool
    timeout_reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.expected_state, str) or not self.expected_state.strip():
            raise ValueError("expected_state is required")
        if not isinstance(self.verification_required, bool):
            raise TypeError("verification_required must be bool")
        if not isinstance(self.timeout_reference, str) or not self.timeout_reference.strip():
            raise ValueError("timeout_reference is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_state": self.expected_state,
            "verification_required": self.verification_required,
            "timeout_reference": self.timeout_reference,
        }


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, frozenset)):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class ActuatorIntent:
    """Immutable description of a requested actuator operation."""

    intent_id: str
    trace_id: str
    source: str
    requested_operation: ActuatorOperation
    target: Any
    reason: str
    owner: str
    trigger: ActuatorTrigger
    rollback_policy: RollbackPolicy
    safety_context: SafetyContext
    verification_expectation: PhysicalVerificationExpectation

    def __post_init__(self) -> None:
        for field_name in ("intent_id", "trace_id", "source", "reason", "owner"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required")
        if not isinstance(self.requested_operation, ActuatorOperation):
            try:
                object.__setattr__(
                    self,
                    "requested_operation",
                    ActuatorOperation(self.requested_operation),
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid requested_operation") from exc
        if not isinstance(self.trigger, ActuatorTrigger):
            try:
                object.__setattr__(self, "trigger", ActuatorTrigger(self.trigger))
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid trigger") from exc
        if not isinstance(self.rollback_policy, RollbackPolicy):
            try:
                object.__setattr__(self, "rollback_policy", RollbackPolicy(self.rollback_policy))
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid rollback_policy") from exc
        if not isinstance(self.safety_context, SafetyContext):
            raise TypeError("typed SafetyContext is required")
        if not isinstance(self.verification_expectation, PhysicalVerificationExpectation):
            raise TypeError("typed PhysicalVerificationExpectation is required")

    @classmethod
    def new(
        cls,
        *,
        trace_id: str,
        source: str,
        requested_operation: ActuatorOperation,
        target: Any,
        reason: str,
        owner: str,
        trigger: ActuatorTrigger,
        rollback_policy: RollbackPolicy,
        safety_context: SafetyContext,
        verification_expectation: PhysicalVerificationExpectation,
    ) -> "ActuatorIntent":
        return cls(
            intent_id=uuid4().hex,
            trace_id=trace_id,
            source=source,
            requested_operation=requested_operation,
            target=target,
            reason=reason,
            owner=owner,
            trigger=trigger,
            rollback_policy=rollback_policy,
            safety_context=safety_context,
            verification_expectation=verification_expectation,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "trace_id": self.trace_id,
            "source": self.source,
            "requested_operation": self.requested_operation.value,
            "target": _plain(self.target),
            "reason": self.reason,
            "owner": self.owner,
            "trigger": self.trigger.value,
            "rollback_policy": self.rollback_policy.value,
            "safety_context": self.safety_context.to_dict(),
            "verification_expectation": self.verification_expectation.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ActuatorIntent":
        required = {
            "intent_id",
            "trace_id",
            "source",
            "requested_operation",
            "target",
            "reason",
            "owner",
            "trigger",
            "rollback_policy",
            "safety_context",
            "verification_expectation",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError("missing ActuatorIntent fields: " + ", ".join(missing))
        context = payload["safety_context"]
        expectation = payload["verification_expectation"]
        if not isinstance(context, Mapping) or not isinstance(expectation, Mapping):
            raise TypeError("nested ActuatorIntent contracts must be mappings")
        return cls(
            intent_id=str(payload["intent_id"]),
            trace_id=str(payload["trace_id"]),
            source=str(payload["source"]),
            requested_operation=ActuatorOperation(payload["requested_operation"]),
            target=payload["target"],
            reason=str(payload["reason"]),
            owner=str(payload["owner"]),
            trigger=ActuatorTrigger(payload["trigger"]),
            rollback_policy=RollbackPolicy(payload["rollback_policy"]),
            safety_context=SafetyContext(**dict(context)),
            verification_expectation=PhysicalVerificationExpectation(**dict(expectation)),
        )


@dataclass(frozen=True)
class ExistingActuatorRequest:
    """Transport-free observation of a current request before normalization."""

    source: str
    operation: ActuatorOperation
    target: Any
    reason: str
    owner: str
    trigger: ActuatorTrigger
    rollback_policy: RollbackPolicy
    safety_context: SafetyContext
    verification_expectation: PhysicalVerificationExpectation


def map_existing_request(request: ExistingActuatorRequest, *, trace_id: str) -> ActuatorIntent:
    """Map an existing request to an intent without executing it."""
    return ActuatorIntent.new(
        trace_id=trace_id,
        source=request.source,
        requested_operation=request.operation,
        target=request.target,
        reason=request.reason,
        owner=request.owner,
        trigger=request.trigger,
        rollback_policy=request.rollback_policy,
        safety_context=request.safety_context,
        verification_expectation=request.verification_expectation,
    )
