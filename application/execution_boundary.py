"""Transport-free execution boundary contracts and routing validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .actuator_intent import (
    ActuatorIntent,
    PhysicalVerificationExpectation,
    RollbackPolicy,
    SafetyContext,
)
from .containment_result import ContainmentVerificationState


@dataclass(frozen=True)
class ContainmentResultRequest:
    """Application request for an outer containment owner."""

    trace_id: str
    source: str
    trigger: str
    requested_action: str
    owner: str
    safety_context: SafetyContext
    rollback_policy: RollbackPolicy
    verification_expectation: PhysicalVerificationExpectation


@dataclass(frozen=True)
class ExecutionRequest:
    """Validated request handed to a future adapter, never executed here."""

    intent: ActuatorIntent | None
    containment: ContainmentResultRequest | None
    owner: str
    trigger: str
    safety_context: SafetyContext
    rollback_policy: RollbackPolicy
    verification_expectation: PhysicalVerificationExpectation
    trace_id: str
    correlation: Mapping[str, Any]


@dataclass(frozen=True)
class ExecutionResult:
    """Result of boundary validation/routing, not a physical result."""

    accepted: bool
    rejected: bool
    deferred: bool
    verification_state: ContainmentVerificationState
    reason: str
    request: ExecutionRequest | None = None


class ExecutionDispatcher:
    """Validate and route requests without calling an execution adapter."""

    ALLOWED_OWNERS = frozenset(
        {
            "V2 transaction owner",
            "V2 runtime safety surface",
            "SafeOutputCoordinator",
            "V2 watchdog + safety",
            "Manual manager + safety",
        }
    )

    def dispatch_intent(self, intent: ActuatorIntent, *, correlation: Mapping[str, Any] | None = None) -> ExecutionResult:
        if not isinstance(intent, ActuatorIntent):
            return self._reject("invalid_actuator_intent")
        try:
            request = ExecutionRequest(
                intent=intent,
                containment=None,
                owner=intent.owner,
                trigger=intent.trigger.value,
                safety_context=intent.safety_context,
                rollback_policy=intent.rollback_policy,
                verification_expectation=intent.verification_expectation,
                trace_id=intent.trace_id,
                correlation=dict(correlation or {}),
            )
            self._validate(request)
        except (TypeError, ValueError) as exc:
            return self._reject(str(exc))
        return self._deferred(request, "actuator_intent_deferred")

    def dispatch_containment(self, request: ContainmentResultRequest, *, correlation: Mapping[str, Any] | None = None) -> ExecutionResult:
        if not isinstance(request, ContainmentResultRequest):
            return self._reject("invalid_containment_request")
        try:
            execution = ExecutionRequest(
                intent=None,
                containment=request,
                owner=request.owner,
                trigger=request.trigger,
                safety_context=request.safety_context,
                rollback_policy=request.rollback_policy,
                verification_expectation=request.verification_expectation,
                trace_id=request.trace_id,
                correlation=dict(correlation or {}),
            )
            self._validate(execution)
        except (TypeError, ValueError) as exc:
            return self._reject(str(exc))
        return self._deferred(execution, "containment_request_deferred")

    def _validate(self, request: ExecutionRequest) -> None:
        if request.owner not in self.ALLOWED_OWNERS:
            raise ValueError("execution owner is not approved")
        if not request.trace_id.strip() or not request.trigger.strip():
            raise ValueError("trace and trigger are required")
        if not isinstance(request.safety_context, SafetyContext):
            raise TypeError("safety context is required")
        if not isinstance(request.rollback_policy, RollbackPolicy):
            raise TypeError("rollback policy is required")
        if not isinstance(request.verification_expectation, PhysicalVerificationExpectation):
            raise TypeError("verification expectation is required")

    @staticmethod
    def _deferred(request: ExecutionRequest, reason: str) -> ExecutionResult:
        return ExecutionResult(True, False, True, ContainmentVerificationState.NOT_REQUESTED, reason, request)

    @staticmethod
    def _reject(reason: str) -> ExecutionResult:
        return ExecutionResult(False, True, False, ContainmentVerificationState.UNKNOWN, reason)


__all__ = ["ContainmentResultRequest", "ExecutionRequest", "ExecutionResult", "ExecutionDispatcher"]
