"""Fail-closed compatibility surface for the former physical executor."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from runtime.output.execution_policy import ExecutionPolicyDecision
from runtime.output.executor.command_plan import PhysicalCommandPlan, PhysicalCommandStep
from runtime.output.executor.contract import ExecutionLeaseState
from runtime.output.intent import OutputAction, SafeOutputIntent
from runtime.physical.lease import BenchExecutionLease, BenchLeaseProvider

from .audit import PhysicalExecutionAudit
from .capabilities import HardwareCapability
from .configuration import PhysicalExecutionConfig


class PhysicalExecutionError(RuntimeError):
    """Raised when a quarantined independent physical path is requested."""


class PhysicalGateState(str, Enum):
    DISABLED = "DISABLED"
    READY = "READY"
    ARMED = "ARMED"
    EXECUTING = "EXECUTING"
    FAILED = "FAILED"


class PhysicalBridgeTransport(Protocol):
    """Readback-only compatibility protocol."""

    def readback(self) -> Any: ...

    async def read_snapshot(self) -> Any: ...


@dataclass(frozen=True)
class GateValidation:
    allowed: bool
    reason: str
    violations: tuple[str, ...] = ()


class PhysicalExecutionGate:
    """Retained for validation/audit compatibility; it is not an owner."""

    def __init__(self, config: PhysicalExecutionConfig = PhysicalExecutionConfig()):
        self.config = config
        self.state = PhysicalGateState.READY if config.enabled else PhysicalGateState.DISABLED
        self.operator: str | None = None

    def arm(self, operator: str) -> None:
        if not self.config.enabled:
            raise PhysicalExecutionError("physical execution is disabled")
        if self.config.require_manual_arm and not operator.strip():
            raise PhysicalExecutionError("manual operator identity is required")
        self.operator = operator.strip() or "manual"
        self.state = PhysicalGateState.ARMED

    def disarm(self) -> None:
        self.operator = None
        self.state = PhysicalGateState.READY if self.config.enabled else PhysicalGateState.DISABLED

    def validate(self, plan: PhysicalCommandPlan, safety: ExecutionPolicyDecision,
                 lease: ExecutionLeaseState | None, capability: HardwareCapability | None,
                 envelope: Any = None) -> GateValidation:
        violations: list[str] = []
        if not self.config.enabled:
            violations.append("execution_disabled")
        if self.config.require_manual_arm and self.state is not PhysicalGateState.ARMED:
            violations.append("manual_arm_required")
        if not safety.allowed:
            violations.append("safety_policy_denied")
        if lease is None or str(getattr(getattr(lease, "status", None), "value", getattr(lease, "status", None))) != "active":
            violations.append("valid_execution_lease_required")
        if capability is None:
            violations.append("hardware_capability_required")
        if plan.intent.action is OutputAction.ENABLE and (plan.protection_ovp is None or plan.protection_ocp is None):
            violations.append("protection_targets_required")
        if envelope is not None and not envelope.allowed:
            violations.append("hardware_battery_envelope_blocked")
        if violations:
            return GateValidation(False, "EXECUTION_GATE_REJECTED", tuple(violations))
        return GateValidation(True, "EXECUTION_GATE_ACCEPTED")

    def begin(self, validation: GateValidation) -> None:
        if not validation.allowed:
            raise PhysicalExecutionError(validation.reason + ":" + ",".join(validation.violations))
        self.state = PhysicalGateState.EXECUTING

    def complete(self) -> None:
        self.state = PhysicalGateState.READY if self.config.enabled else PhysicalGateState.DISABLED
        self.operator = None

    def fail(self) -> None:
        self.state = PhysicalGateState.FAILED
