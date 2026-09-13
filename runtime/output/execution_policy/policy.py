"""Data-only gate before a future output executor."""

from __future__ import annotations

from dataclasses import dataclass, field

from runtime.diagnostics import SafetyEvidence
from runtime.output.intent import OutputAction, SafeOutputIntent
from runtime.safety.engine import SafetyDecision


@dataclass(frozen=True)
class ExecutionPolicyContext:
    telemetry_fresh: bool = True
    voltage_valid: bool = True
    current_valid: bool = True
    protection_configured: bool = True
    readback_available: bool = True
    authority_allowed: bool = True
    unsafe_state: bool = False


@dataclass(frozen=True)
class ExecutionPolicyDecision:
    allowed: bool
    reason: str
    violations: tuple[str, ...] = ()
    required_checks: tuple[str, ...] = ()
    source_intent: SafeOutputIntent | None = None
    safety_evidence: tuple[SafetyEvidence, ...] = ()


class ExecutionPolicy:
    def evaluate(
        self,
        intent: SafeOutputIntent,
        safety: SafetyDecision,
        context: ExecutionPolicyContext = ExecutionPolicyContext(),
    ) -> ExecutionPolicyDecision:
        required = ["safety_decision"]
        if intent.action is OutputAction.DISABLE:
            return ExecutionPolicyDecision(True, "DISABLE_ALWAYS_ALLOWED", required_checks=tuple(required), source_intent=intent, safety_evidence=safety.source_evidence)
        if not safety.allowed or not context.authority_allowed:
            return self._deny("SAFETY_OR_AUTHORITY_DENIED", ("safety_decision",), intent, safety)
        if intent.action is OutputAction.ENABLE:
            required += ["telemetry_fresh", "voltage_valid", "current_valid", "protection_configured", "readback_available"]
            checks = {
                "telemetry_fresh": context.telemetry_fresh,
                "voltage_valid": context.voltage_valid,
                "current_valid": context.current_valid,
                "protection_configured": context.protection_configured,
                "readback_available": context.readback_available,
            }
        elif intent.action is OutputAction.SET_VOLTAGE:
            required += ["target_voltage", "telemetry_fresh", "voltage_valid"]
            checks = {"target_voltage": intent.target_voltage is not None, "telemetry_fresh": context.telemetry_fresh, "voltage_valid": context.voltage_valid}
        elif intent.action is OutputAction.SET_CURRENT:
            required += ["target_current", "telemetry_fresh", "current_valid"]
            checks = {"target_current": intent.target_current is not None, "telemetry_fresh": context.telemetry_fresh, "current_valid": context.current_valid}
        else:
            required += ["reset_reason", "source_phase", "safe_state"]
            checks = {"reset_reason": bool(intent.source.strip()), "source_phase": bool(intent.source.strip()), "safe_state": not context.unsafe_state}
        failed = tuple(name for name, value in checks.items() if not value)
        if failed:
            return self._deny("EXECUTION_PREREQUISITES_FAILED", required, intent, safety, failed)
        return ExecutionPolicyDecision(True, "EXECUTION_PREREQUISITES_ACCEPTED", required_checks=tuple(required), source_intent=intent, safety_evidence=safety.source_evidence)

    @staticmethod
    def _deny(reason, required, intent, safety, violations=()):
        return ExecutionPolicyDecision(False, reason, tuple(violations), tuple(required), intent, safety.source_evidence)
