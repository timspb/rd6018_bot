"""Pure comparison of V2 execution actions and V3 actuator intents."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .actuator_intent import ActuatorIntent, ActuatorOperation, PhysicalVerificationExpectation, RollbackPolicy, SafetyContext


class ShadowValidationCategory(str, Enum):
    EQUAL = "equal"
    EXPECTED_DIFFERENCE = "expected_difference"
    UNSAFE_DIFFERENCE = "unsafe_difference"
    UNRESOLVED = "unresolved"


class FailureScenario(str, Enum):
    COMMAND_TIMEOUT = "command_timeout"
    READBACK_MISMATCH = "readback_mismatch"
    TELEMETRY_STALE = "telemetry_stale"
    LEASE_EXPIRED = "lease_expired"
    TRANSPORT_UNAVAILABLE = "transport_unavailable"


@dataclass(frozen=True)
class V2ExecutionAction:
    operation: ActuatorOperation
    target: Any
    owner: str
    safety_context: SafetyContext
    rollback_policy: RollbackPolicy
    verification_expectation: PhysicalVerificationExpectation
    adapter: str
    transport_available: bool
    readback_required: bool
    containment: bool = False


@dataclass(frozen=True)
class ShadowValidationResult:
    category: ShadowValidationCategory
    operation: str
    differences: tuple[str, ...]
    safety_valid: bool
    execution_ready: bool
    physical_execution_performed: bool = False


class ExecutionShadowValidator:
    """Validate execution parity without selecting or invoking an executor."""

    def compare(self, v2: V2ExecutionAction, v3: ActuatorIntent) -> ShadowValidationResult:
        if not isinstance(v2, V2ExecutionAction) or not isinstance(v3, ActuatorIntent):
            raise TypeError("V2ExecutionAction and ActuatorIntent are required")
        differences: list[str] = []
        if v2.operation is not v3.requested_operation:
            differences.append("operation")
        if v2.target != v3.target:
            differences.append("target")
        if v2.owner != v3.owner:
            differences.append("owner")
        if v2.safety_context != v3.safety_context:
            differences.append("safety_context")
        if v2.rollback_policy is not v3.rollback_policy:
            differences.append("rollback_policy")
        if v2.verification_expectation != v3.verification_expectation:
            differences.append("verification_expectation")
        if v2.containment and v3.requested_operation is not ActuatorOperation.OUTPUT_OFF:
            differences.append("containment_operation")
        safety_valid = self._safety_valid(v3.safety_context, v3.rollback_policy, v3.verification_expectation)
        ready = safety_valid and bool(v3.owner.strip()) and bool(v2.adapter.strip()) and v2.transport_available
        if v2.readback_required and not v3.verification_expectation.verification_required:
            differences.append("readback_requirement")
            ready = False
        category = ShadowValidationCategory.EQUAL
        if differences:
            category = ShadowValidationCategory.UNSAFE_DIFFERENCE if any(
                item in {"owner", "safety_context", "rollback_policy", "verification_expectation", "containment_operation", "readback_requirement"}
                for item in differences
            ) else ShadowValidationCategory.EXPECTED_DIFFERENCE
        if not v2.transport_available or not v2.adapter.strip():
            category = ShadowValidationCategory.UNRESOLVED
        return ShadowValidationResult(category, v3.requested_operation.value, tuple(differences), safety_valid, ready)

    def validate_failure(self, scenario: FailureScenario, v2: V2ExecutionAction, v3: ActuatorIntent) -> ShadowValidationResult:
        baseline = self.compare(v2, v3)
        if not isinstance(scenario, FailureScenario):
            scenario = FailureScenario(scenario)
        failure_differences = list(baseline.differences)
        if scenario in {FailureScenario.COMMAND_TIMEOUT, FailureScenario.READBACK_MISMATCH}:
            if v3.rollback_policy is RollbackPolicy.NONE or not v3.verification_expectation.verification_required:
                failure_differences.append(scenario.value)
                return ShadowValidationResult(ShadowValidationCategory.UNSAFE_DIFFERENCE, baseline.operation, tuple(failure_differences), False, False)
        elif scenario in {FailureScenario.TELEMETRY_STALE, FailureScenario.LEASE_EXPIRED, FailureScenario.TRANSPORT_UNAVAILABLE}:
            if not v3.safety_context.telemetry_state or not v3.safety_context.lease_state:
                failure_differences.append(scenario.value)
                return ShadowValidationResult(ShadowValidationCategory.UNRESOLVED, baseline.operation, tuple(failure_differences), False, False)
        return ShadowValidationResult(baseline.category, baseline.operation, tuple(failure_differences), baseline.safety_valid, False)

    @staticmethod
    def _safety_valid(context: SafetyContext, rollback: RollbackPolicy, verification: PhysicalVerificationExpectation) -> bool:
        return (
            isinstance(context, SafetyContext)
            and bool(context.telemetry_state.strip())
            and bool(context.lease_state.strip())
            and bool(context.containment_state.strip())
            and bool(context.verification_state.strip())
            and bool(context.limits_reference.strip())
            and isinstance(rollback, RollbackPolicy)
            and rollback is not RollbackPolicy.NONE
            and isinstance(verification, PhysicalVerificationExpectation)
            and verification.verification_required
        )


__all__ = [
    "ShadowValidationCategory", "FailureScenario", "V2ExecutionAction",
    "ShadowValidationResult", "ExecutionShadowValidator",
]
