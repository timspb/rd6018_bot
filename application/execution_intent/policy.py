"""Pure safety policy boundary for execution intents."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .models import ExecutionIntent, IntentValidationResult, SafetyOutcome


class SafetyPolicy(Protocol):
    def validate(self, intent: ExecutionIntent) -> IntentValidationResult: ...


class ExecutionSafetyPolicy:
    """Data-only allow/limit/deny policy; it performs no safety action itself."""

    def __init__(self, *, max_voltage_v: float, max_current_a: float, enabled: bool = True) -> None:
        if max_voltage_v < 0 or max_current_a < 0:
            raise ValueError("safety limits cannot be negative")
        self.max_voltage_v = float(max_voltage_v)
        self.max_current_a = float(max_current_a)
        self.enabled = bool(enabled)

    def validate(self, intent: ExecutionIntent) -> IntentValidationResult:
        if not self.enabled:
            return IntentValidationResult(SafetyOutcome.DENIED, None, "safety policy is disabled")
        context = intent.safety_context
        if context.containment_state.upper() not in {"NORMAL", "OBSERVE"}:
            return IntentValidationResult(SafetyOutcome.DENIED, None, "containment state forbids execution intent")
        if context.telemetry_state.upper() in {"UNKNOWN", "STALE", "INVALID"}:
            return IntentValidationResult(SafetyOutcome.DENIED, None, "telemetry state is not execution-ready")
        limited_v = min(float(intent.requested_voltage_v), self.max_voltage_v)
        limited_i = min(float(intent.requested_current_a), self.max_current_a)
        if limited_v <= 0 or limited_i <= 0:
            return IntentValidationResult(SafetyOutcome.DENIED, None, "zero setpoint is not an execution intent")
        if limited_v != intent.requested_voltage_v or limited_i != intent.requested_current_a:
            return IntentValidationResult(
                SafetyOutcome.LIMITED,
                replace(intent, requested_voltage_v=limited_v, requested_current_a=limited_i),
                "intent limited by safety policy",
            )
        return IntentValidationResult(SafetyOutcome.ALLOWED, intent, "intent allowed by safety policy")
