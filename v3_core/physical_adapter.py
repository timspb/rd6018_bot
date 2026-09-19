"""V3 physical adapter contract backed only by an injected bench transport."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .bench_transport import BenchTransport, TransportResult
from .configuration import ConfigurationAuthority
from .contracts import ActuatorIntent, ActuatorOperation, ExecutionResult


class AdapterVerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    STALE = "STALE"


@dataclass(frozen=True)
class PhysicalAdapterConfig:
    command_timeout_s: float
    readback_timeout_s: float
    readback_tolerance: float

    @classmethod
    def from_authority(cls, authority: ConfigurationAuthority, values: dict[str, Any] | None = None) -> "PhysicalAdapterConfig":
        resolved = authority.resolve(values or {})
        return cls(resolved["execution.command_timeout_s"], resolved["execution.readback_timeout_s"], resolved["execution.readback_tolerance"])


@dataclass(frozen=True)
class AdapterExecutionResult:
    requested_action: str
    transport_result: TransportResult
    observed_state: Any
    verification_status: AdapterVerificationStatus
    failure_reason: str | None
    trace_id: str
    rollback_required: bool


@dataclass(frozen=True)
class ContainmentRequest:
    trace_id: str
    reason: str
    owner: str = "V3 Safety Domain"


class V3PhysicalAdapter:
    """Translate and verify commands; never owns safety decisions or I/O."""

    OWNER = "V3 Execution Boundary"

    def __init__(self, transport: BenchTransport, config: PhysicalAdapterConfig, *, clock=None) -> None:
        self.transport = transport
        self.config = config
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(self, intent: ActuatorIntent) -> AdapterExecutionResult:
        if intent.owner != self.OWNER:
            raise ValueError("duplicate or unapproved execution owner")
        action, target = self._translate(intent.operation, intent.target)
        result = self.transport.send(action, target)
        status, failure = self._verify(result, intent)
        return AdapterExecutionResult(action, result, result.observed_state, status, failure, intent.trace_id, status is not AdapterVerificationStatus.VERIFIED)

    def submit(self, intent: ActuatorIntent) -> ExecutionResult:
        """ExecutionDispatcher adapter protocol; still bench-only."""
        result = self.execute(intent)
        return ExecutionResult(
            accepted=result.transport_result.accepted,
            executed=False,
            operation=intent.operation,
            reason=result.failure_reason or result.verification_status.value,
            trace_id=result.trace_id,
        )

    def rollback(self, intent: ActuatorIntent) -> ActuatorIntent:
        return ActuatorIntent(ActuatorOperation.OUTPUT_OFF, None, "rollback:" + intent.reason, intent.trace_id, self.OWNER)

    def containment(self, request: ContainmentRequest) -> ActuatorIntent:
        if request.owner != "V3 Safety Domain":
            raise ValueError("unapproved safety owner")
        return ActuatorIntent(ActuatorOperation.CONTAINMENT, None, request.reason, request.trace_id, self.OWNER)

    def _translate(self, operation: ActuatorOperation, target: Any) -> tuple[str, Any]:
        if operation is ActuatorOperation.OUTPUT_ON:
            return "OUTPUT_ON", True
        if operation is ActuatorOperation.OUTPUT_OFF:
            return "OUTPUT_OFF", False
        if operation is ActuatorOperation.SET_VOLTAGE:
            return "SET_VOLTAGE", target
        if operation is ActuatorOperation.SET_CURRENT:
            return "SET_CURRENT", target
        if operation in {ActuatorOperation.STOP, ActuatorOperation.CONTAINMENT}:
            return "OUTPUT_OFF", False
        raise ValueError("unsupported actuator operation")

    def _verify(self, result: TransportResult, intent: ActuatorIntent) -> tuple[AdapterVerificationStatus, str | None]:
        if result.timed_out:
            return AdapterVerificationStatus.TIMEOUT, result.reason
        if result.unavailable or not result.accepted:
            return AdapterVerificationStatus.FAILED, result.reason
        if result.observed_at is None:
            return AdapterVerificationStatus.UNVERIFIED, "readback_timestamp_missing"
        age = max(0.0, (self.clock() - result.observed_at).total_seconds())
        if age > self.config.readback_timeout_s:
            return AdapterVerificationStatus.STALE, "readback_stale"
        expected = intent.target if intent.operation in {ActuatorOperation.SET_VOLTAGE, ActuatorOperation.SET_CURRENT} else intent.operation is ActuatorOperation.OUTPUT_ON
        observed = result.observed_state
        try:
            matches = abs(float(expected) - float(observed)) <= self.config.readback_tolerance
        except (TypeError, ValueError):
            matches = expected == observed
        return (AdapterVerificationStatus.VERIFIED, None) if matches else (AdapterVerificationStatus.FAILED, "readback_mismatch")


__all__ = ["AdapterVerificationStatus", "PhysicalAdapterConfig", "AdapterExecutionResult", "ContainmentRequest", "V3PhysicalAdapter"]
