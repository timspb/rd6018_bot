"""Configurable V3 safety policy with no hardcoded RD values."""

from __future__ import annotations

from dataclasses import dataclass

from .models import SafetyContext, SafetyDecision, SafetyState


@dataclass(frozen=True)
class SafetyPolicy:
    """Limits are supplied by the caller/configuration authority."""

    max_voltage_v: float
    max_current_a: float
    max_temperature_c: float
    emergency_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.max_voltage_v <= 0 or self.max_current_a <= 0 or self.max_temperature_c <= 0:
            raise ValueError("safety limits must be positive")

    def evaluate(self, context: SafetyContext) -> SafetyDecision:
        rules: list[str] = []
        if context.emergency:
            return SafetyDecision(SafetyState.EMERGENCY, "explicit emergency condition", ("emergency",), "HIGH", context.timestamp)
        if any(code in self.emergency_codes for code in context.protection_codes):
            return SafetyDecision(SafetyState.EMERGENCY, "emergency protection code", ("protection_code",), "HIGH", context.timestamp)
        if not context.telemetry_present:
            return SafetyDecision(SafetyState.DENY, "telemetry is missing", ("missing_telemetry",), "HIGH", context.timestamp)
        if not context.telemetry_fresh:
            return SafetyDecision(SafetyState.DENY, "telemetry is stale", ("stale_telemetry",), "HIGH", context.timestamp)
        if context.voltage_v is not None and context.voltage_v > self.max_voltage_v:
            rules.append("OVP")
        if context.current_a is not None and context.current_a > self.max_current_a:
            rules.append("OCP")
        if any(value is not None and value > self.max_temperature_c for value in context.temperatures_c):
            rules.append("OTP")
        if rules:
            return SafetyDecision(SafetyState.DENY, "configured safety limit exceeded", tuple(rules), "HIGH", context.timestamp)
        return SafetyDecision(SafetyState.ALLOW, "all configured safety checks passed", (), "HIGH", context.timestamp)


__all__ = ["SafetyPolicy"]
