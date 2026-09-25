"""Opt-in physical bridge with a closed manual execution gate.

This module has no RD, HA, GPIO, or transport implementation. A transport is
injected by a future bench-only integration and is never created here.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from runtime.output.execution_policy import ExecutionPolicyDecision
from runtime.output.executor.command_plan import PhysicalCommandPlan, PhysicalCommandStep
from runtime.output.executor.contract import ExecutionLeaseState
from runtime.output.intent import OutputAction, SafeOutputIntent
from runtime.physical.lease import BenchExecutionLease, BenchLeaseProvider, BenchLeaseScope

from .audit import PhysicalExecutionAudit
from .capabilities import HardwareCapability
from .configuration import PhysicalExecutionConfig


class PhysicalExecutionError(RuntimeError):
    """Raised when the manual physical execution gate rejects a plan."""


class PhysicalGateState(str, Enum):
    DISABLED = "DISABLED"
    READY = "READY"
    ARMED = "ARMED"
    EXECUTING = "EXECUTING"
    FAILED = "FAILED"


class PhysicalBridgeTransport(Protocol):
    """Only the future bench transport implements these physical operations."""

    def apply(self, action: str, **values: Any) -> Any: ...

    def readback(self) -> Any: ...

    async def disable_output(self) -> None: ...

    async def read_snapshot(self) -> Any: ...


@dataclass(frozen=True)
class GateValidation:
    allowed: bool
    reason: str
    violations: tuple[str, ...] = ()


class PhysicalExecutionGate:
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
        violations = []
        if not self.config.enabled:
            violations.append("execution_disabled")
        if self.config.require_manual_arm and self.state is not PhysicalGateState.ARMED:
            violations.append("manual_arm_required")
        if not safety.allowed:
            violations.append("safety_policy_denied")
        lease_status = getattr(lease, "status", None)
        lease_owner = getattr(lease, "owner", None) or getattr(lease, "operator", None)
        if lease is None or str(getattr(lease_status, "value", lease_status)) != "active" or not lease_owner:
            violations.append("valid_execution_lease_required")
        if capability is None:
            violations.append("hardware_capability_required")
        elif not _capability_supports(plan, capability):
            violations.append("hardware_capability_mismatch")
        if plan.intent.action is OutputAction.ENABLE and (plan.protection_ovp is None or plan.protection_ocp is None):
            violations.append("protection_targets_required")
        if envelope is not None and not envelope.allowed:
            violations.append("hardware_battery_envelope_blocked")
        if violations:
            return GateValidation(False, "EXECUTION_GATE_REJECTED", tuple(violations))
        return GateValidation(True, "EXECUTION_GATE_ACCEPTED")

    def begin(self, validation: GateValidation) -> None:
        if not validation.allowed:
            raise PhysicalExecutionError(validation.reason + ": " + ",".join(validation.violations))
        self.state = PhysicalGateState.EXECUTING

    def complete(self) -> None:
        self.state = PhysicalGateState.READY if self.config.enabled else PhysicalGateState.DISABLED
        self.operator = None

    def fail(self) -> None:
        self.state = PhysicalGateState.FAILED


def _capability_supports(plan: PhysicalCommandPlan, capability: HardwareCapability) -> bool:
    action = plan.intent.action
    if action is OutputAction.ENABLE:
        return (capability.supports_enable and capability.supports_ovp and capability.supports_ocp
                and capability.supports_voltage_readback and capability.supports_current_readback
                and capability.supports_output_state_readback)
    if action is OutputAction.DISABLE:
        return capability.supports_disable and capability.supports_output_state_readback
    if action is OutputAction.RESET_PROTECTION:
        return capability.supports_reset_protection
    return True


class PhysicalBridgeExecutor:
    """Executes a plan only after the explicit manual gate accepts it."""

    def __init__(self, gate: PhysicalExecutionGate, transport: PhysicalBridgeTransport,
                 audit: PhysicalExecutionAudit | None = None):
        self.gate = gate
        self.transport = transport
        self.audit = audit or PhysicalExecutionAudit()

    def prepare(self, plan: PhysicalCommandPlan, safety: ExecutionPolicyDecision,
                lease: ExecutionLeaseState | None, capability: HardwareCapability | None, envelope: Any = None) -> GateValidation:
        validation = self.gate.validate(plan, safety, lease, capability, envelope)
        self.audit.record(plan, self.gate.operator or "unknown", self.gate.state.value, result=validation.reason, error=None if validation.allowed else ";".join(validation.violations))
        return validation

    def execute(self, plan: PhysicalCommandPlan, safety: ExecutionPolicyDecision,
                lease: ExecutionLeaseState | None, capability: HardwareCapability | None, envelope: Any = None):
        validation = self.prepare(plan, safety, lease, capability, envelope)
        if not validation.allowed:
            raise PhysicalExecutionError(validation.reason + ": " + ",".join(validation.violations))
        self.gate.begin(validation)
        actions = []
        readback = None
        try:
            for step in plan.steps:
                if step.name == "prepare":
                    continue
                if step.name in {"readback_compare", "read_output_state"}:
                    readback = self.transport.readback()
                    actions.append(step.name)
                    if readback is None:
                        raise PhysicalExecutionError("required readback is missing")
                    if step.name == "read_output_state" and _readback_value(readback, "output_state") is True:
                        raise PhysicalExecutionError("verified-off requirement failed")
                    continue
                if step.name == "confirm_off":
                    if _readback_value(readback, "output_state") is not False:
                        raise PhysicalExecutionError("output OFF was not confirmed")
                    actions.append(step.name)
                    continue
                values = {}
                if step.name == "set_voltage":
                    values["value"] = plan.intent.target_voltage
                elif step.name == "set_current":
                    values["value"] = plan.intent.target_current
                elif step.name == "set_ovp":
                    values["value"] = plan.protection_ovp
                elif step.name == "set_ocp":
                    values["value"] = plan.protection_ocp
                self.transport.apply(step.name, **values)
                actions.append(step.name)
            if plan.intent.action is OutputAction.ENABLE:
                readback = self.transport.readback()
                if _readback_value(readback, "output_state") is not True:
                    raise PhysicalExecutionError("output ON was not confirmed")
            record = self.audit.record(plan, self.gate.operator or "unknown", self.gate.state.value, actions=actions, readback=readback, result="EXECUTED")
            self.gate.complete()
            return record
        except Exception as exc:
            self.gate.fail()
            self.audit.record(plan, self.gate.operator or "unknown", self.gate.state.value, actions=actions, result="FAILED", error=str(exc))
            raise

    def verify(self, plan: PhysicalCommandPlan):
        readback = self.transport.readback()
        if readback is None:
            raise PhysicalExecutionError("verification readback is missing")
        return self.audit.record(
            plan, self.gate.operator or "unknown", self.gate.state.value,
            actions=("verify_readback",), readback=readback, result="VERIFIED",
        )

    async def execute_verified_disable(self, plan: PhysicalCommandPlan, safety: ExecutionPolicyDecision,
                                       lease: BenchExecutionLease | None, capability: HardwareCapability | None,
                                       envelope: Any = None, *, lease_provider: BenchLeaseProvider | None = None):
        """Execute only the verified-off plan on an async read/write transport."""
        if plan.intent.action is not OutputAction.DISABLE:
            raise PhysicalExecutionError("verified-disable executor accepts DISABLE_OUTPUT only")
        if lease_provider is None or not lease_provider.validate(lease, BenchLeaseScope.DISABLE_OUTPUT_ONLY):
            raise PhysicalExecutionError("valid DISABLE_OUTPUT bench lease is required")
        validation = self.prepare(plan, safety, lease, capability, envelope)
        if not validation.allowed:
            raise PhysicalExecutionError(validation.reason + ":" + ",".join(validation.violations))
        before = await self.transport.read_snapshot()
        self.gate.begin(validation)
        actions = ["before_snapshot"]
        try:
            await self.transport.disable_output()
            actions.append("disable_output")
            after = await self.transport.read_snapshot()
            actions.extend(("read_output_state", "verify_off", "verify_current"))
            if after is None or getattr(after, "output_state", None) is not False:
                raise PhysicalExecutionError("output OFF was not confirmed")
            current = getattr(after, "measured_current", None)
            if current is None or abs(float(current)) > 0.01:
                raise PhysicalExecutionError("zero-current readback was not confirmed")
            record = self.audit.record(plan, self.gate.operator or "unknown", self.gate.state.value,
                                       actions=actions, readback={"before": before, "after": after}, result="EXECUTED")
            self.gate.complete()
            return record
        except Exception as exc:
            self.gate.fail()
            self.audit.record(plan, self.gate.operator or "unknown", self.gate.state.value,
                              actions=actions, readback={"before": before}, result="FAILED", error=str(exc))
            raise

    async def execute_controlled_transition(self, plan: PhysicalCommandPlan, safety: ExecutionPolicyDecision,
                                             lease: BenchExecutionLease | None, capability: HardwareCapability | None,
                                             *, lease_provider: BenchLeaseProvider | None = None,
                                             envelope: Any = None, parameters: dict[str, float],
                                             tolerances: dict[str, float] | None = None,
                                             readback_timeout_s: float = 5.0,
                                             readback_poll_interval_s: float = 0.5,
                                             on_hold_seconds: float = 0.0,
                                             off_timeout_s: float = 5.0,
                                             off_poll_interval_s: float = 0.5):
        """Bench-only OFF->ON->OFF flow with parameter and state readback."""
        if lease_provider is None or lease is None or not lease_provider.validate(lease, BenchLeaseScope.CONTROLLED_STATE_TRANSITION):
            raise PhysicalExecutionError("valid bench lease is required")
        if plan.intent.action is not OutputAction.ENABLE:
            raise PhysicalExecutionError("controlled transition requires ENABLE plan")
        validation = self.prepare(plan, safety, lease, capability, envelope)
        if not validation.allowed:
            raise PhysicalExecutionError(validation.reason + ":" + ",".join(validation.violations))
        before = await self.transport.read_snapshot()
        actions = ["before_snapshot"]
        self.gate.begin(validation)
        try:
            for name, method in (("set_voltage", "set_voltage"), ("set_current", "set_current"),
                                 ("set_ovp", "set_ovp"), ("set_ocp", "set_ocp")):
                await getattr(self.transport, method)(parameters[name])
                actions.append(name)
                field = {"set_voltage": "voltage_setpoint", "set_current": "current_setpoint",
                         "set_ovp": "ovp", "set_ocp": "ocp"}[name]
                programmed = await _wait_for_setpoint(
                    self.transport, field, parameters[name], tolerances or {},
                    timeout_s=readback_timeout_s, poll_interval_s=readback_poll_interval_s,
                )
                if programmed is None:
                    raise PhysicalExecutionError(f"{name} readback missing")
            programmed = await self.transport.read_snapshot()
            actions.append("readback_parameters")
            expected = {"voltage_setpoint": parameters["set_voltage"], "current_setpoint": parameters["set_current"],
                        "ovp": parameters["set_ovp"], "ocp": parameters["set_ocp"]}
            tolerances = tolerances or {}
            for field, value in expected.items():
                actual = getattr(programmed, {"voltage_setpoint": "configured_voltage", "current_setpoint": "configured_current"}.get(field, field))
                if actual is None or abs(float(actual) - value) > tolerances.get(field, 0.0):
                    raise PhysicalExecutionError(f"{field} readback mismatch")
            await self.transport.enable_output()
            actions.append("enable_output")
            on = await self.transport.read_snapshot()
            actions.append("verify_on")
            if on is None or on.output_state is not True:
                raise PhysicalExecutionError("output ON was not confirmed")
            if on_hold_seconds < 0:
                raise PhysicalExecutionError("invalid ON hold configuration")
            await asyncio.sleep(on_hold_seconds)
            actions.append("on_hold")
            await self.transport.disable_output()
            actions.append("disable_output")
            off = await _wait_for_off(
                self.transport, tolerances.get("measured_current", 0.0) if tolerances else 0.0,
                timeout_s=off_timeout_s, poll_interval_s=off_poll_interval_s,
            )
            actions.append("verify_off")
            if off is None or off.output_state is not False or off.measured_current is None or abs(float(off.measured_current)) > tolerances.get("measured_current", 0.0):
                raise PhysicalExecutionError("output OFF and zero-current were not confirmed")
            record = self.audit.record(plan, self.gate.operator or "unknown", self.gate.state.value,
                                       actions=actions, readback={"before": before, "parameters": programmed, "on": on, "off": off}, result="EXECUTED")
            self.gate.complete()
            return record
        except Exception as exc:
            self.gate.fail()
            self.audit.record(plan, self.gate.operator or "unknown", self.gate.state.value,
                              actions=actions, readback={"before": before}, result="FAILED", error=str(exc))
            raise

    def rollback(self, plan: PhysicalCommandPlan, safety: ExecutionPolicyDecision,
                 lease: ExecutionLeaseState | None, capability: HardwareCapability | None):
        disable_plan = build_disable_plan()
        return self.execute(disable_plan, safety, lease, capability)


async def _wait_for_setpoint(transport: PhysicalBridgeTransport, field: str, expected: float,
                             tolerances: dict[str, float], *, timeout_s: float,
                             poll_interval_s: float):
    if timeout_s < 0 or poll_interval_s <= 0:
        raise PhysicalExecutionError("invalid readback polling configuration")
    field_name = {"voltage_setpoint": "configured_voltage", "current_setpoint": "configured_current"}.get(field, field)
    deadline = time.monotonic() + timeout_s
    while True:
        snapshot = await transport.read_snapshot()
        actual = getattr(snapshot, field_name, None) if snapshot is not None else None
        tolerance = tolerances.get(field)
        if actual is not None and tolerance is not None and abs(float(actual) - expected) <= tolerance:
            return snapshot
        if time.monotonic() >= deadline:
            return snapshot
        await asyncio.sleep(poll_interval_s)


async def _wait_for_off(transport: PhysicalBridgeTransport, current_tolerance: float, *,
                        timeout_s: float, poll_interval_s: float):
    if timeout_s < 0 or poll_interval_s <= 0:
        raise PhysicalExecutionError("invalid OFF polling configuration")
    deadline = time.monotonic() + timeout_s
    last = None
    while True:
        last = await transport.read_snapshot()
        current = getattr(last, "measured_current", None) if last is not None else None
        if (last is not None and last.output_state is False and current is not None
                and abs(float(current)) <= current_tolerance):
            return last
        if time.monotonic() >= deadline:
            return last
        await asyncio.sleep(poll_interval_s)

def _readback_value(readback: Any, name: str) -> Any:
    return readback.get(name) if isinstance(readback, dict) else getattr(readback, name, None)


def build_disable_plan() -> PhysicalCommandPlan:
    """Build the only rollback action: verified disable then protection reset."""
    return PhysicalCommandPlan(
        intent=SafeOutputIntent(OutputAction.DISABLE, source="physical_bridge:rollback"),
        steps=(
            PhysicalCommandStep("disable"),
            PhysicalCommandStep("read_output_state", True),
            PhysicalCommandStep("confirm_off", True),
            PhysicalCommandStep("reset_protection"),
        ),
    )
