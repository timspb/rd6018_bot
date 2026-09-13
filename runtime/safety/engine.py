"""Pure validation of charge intent against safety data and limits."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple

from runtime.charge.intent import ChargeIntent
from runtime.charge.measurements import Measurements


@dataclass(frozen=True)
class SafetyLimits:
    max_voltage: float
    max_current: float
    max_temperature: Optional[float] = None

    def __post_init__(self) -> None:
        if self.max_voltage <= 0 or self.max_current <= 0:
            raise ValueError("safety limits must be positive")
        if self.max_temperature is not None and self.max_temperature <= 0:
            raise ValueError("maximum temperature must be positive")


@dataclass(frozen=True)
class SafetyContext:
    telemetry_valid: bool = True
    ownership_allowed: bool = True


@dataclass(frozen=True)
class SafetyDecision:
    accepted: bool
    reason: str
    limits_applied: Mapping[str, float] = field(default_factory=dict)


class SafetyEngine:
    """Return a safety decision without applying an intent."""

    def __init__(self, limits: SafetyLimits) -> None:
        self.limits = limits

    def evaluate(
        self,
        intent: ChargeIntent,
        measurements: Measurements,
        state: SafetyContext,
    ) -> SafetyDecision:
        if not state.telemetry_valid:
            return SafetyDecision(False, "TELEMETRY_INVALID", self._limits())
        if not state.ownership_allowed:
            return SafetyDecision(False, "OWNERSHIP_NOT_ALLOWED", self._limits())
        if self.limits.max_temperature is not None and measurements.temperature is not None:
            if measurements.temperature >= self.limits.max_temperature:
                return SafetyDecision(False, "TEMPERATURE_LIMIT", self._limits())
        if intent.completed and intent.target_voltage is None and intent.target_current is None:
            return SafetyDecision(True, "COMPLETED_INTENT", self._limits())
        if intent.target_voltage is None or intent.target_current is None:
            return SafetyDecision(False, "INCOMPLETE_TARGETS", self._limits())
        if intent.target_voltage <= 0 or intent.target_current <= 0:
            return SafetyDecision(False, "NON_POSITIVE_TARGET", self._limits())
        if intent.target_voltage > self.limits.max_voltage:
            return SafetyDecision(False, "VOLTAGE_LIMIT", self._limits())
        if intent.target_current > self.limits.max_current:
            return SafetyDecision(False, "CURRENT_LIMIT", self._limits())
        return SafetyDecision(True, "ACCEPTED", self._limits())

    def _limits(self) -> Mapping[str, float]:
        limits = {"max_voltage": self.limits.max_voltage, "max_current": self.limits.max_current}
        if self.limits.max_temperature is not None:
            limits["max_temperature"] = self.limits.max_temperature
        return limits
