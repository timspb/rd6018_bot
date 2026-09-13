"""Pure V3 safety-policy validation; no physical or transport dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from runtime.charge.battery import BatteryProfile
from runtime.charge.intent import ChargeIntent
from runtime.charge.measurements import Measurements
from runtime.output.intent import SafeOutputIntent


@dataclass(frozen=True)
class SafetyViolation:
    type: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class SafetyLimits:
    """Configured policy data; this class does not apply limits to hardware."""

    max_voltage: float
    max_current: float
    max_temperature: Optional[float] = None
    telemetry_max_age_seconds: Optional[float] = None

    def __post_init__(self) -> None:
        if self.max_voltage <= 0 or self.max_current <= 0:
            raise ValueError("safety limits must be positive")
        if self.max_temperature is not None and self.max_temperature <= 0:
            raise ValueError("maximum temperature must be positive")
        if self.telemetry_max_age_seconds is not None and self.telemetry_max_age_seconds < 0:
            raise ValueError("telemetry max age must not be negative")


@dataclass(frozen=True)
class SafetyContext:
    telemetry_valid: bool = True
    ownership_allowed: bool = True
    profile: BatteryProfile | None = None
    strategy_available: bool = True
    allowed_next_stages: frozenset[str] | None = None
    now: float | None = None
    mix_authority_exhausted: bool = False


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str
    violations: tuple[SafetyViolation, ...] = ()
    limits_applied: Mapping[str, float] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        """Compatibility alias for the Phase 8A shadow contract."""

        return self.allowed


class SafetyEngine:
    """Validate an intent and return a decision without applying it."""

    def __init__(self, limits: SafetyLimits) -> None:
        self.limits = limits

    def evaluate(self, intent: ChargeIntent, measurements: Measurements, state: SafetyContext) -> SafetyDecision:
        violation = self._context_violation(measurements, state)
        if violation is not None:
            return self._reject(violation)
        violations = self._intent_violations(intent, state)
        if violations:
            return self._reject(violations[0], tuple(violations))
        if intent.completed and intent.target_voltage is None and intent.target_current is None:
            return self._accept("COMPLETED_INTENT")
        return self._accept("ACCEPTED")

    def _context_violation(self, measurements: Measurements, state: SafetyContext) -> SafetyViolation | None:
        if not state.telemetry_valid:
            return SafetyViolation("telemetry", "telemetry is invalid")
        if not state.ownership_allowed:
            return SafetyViolation("ownership", "ownership is not allowed")
        if not state.strategy_available:
            return SafetyViolation("strategy", "charge strategy is unavailable")
        max_age = self.limits.telemetry_max_age_seconds
        if max_age is not None:
            if state.now is None or measurements.time is None or state.now - measurements.time > max_age:
                return SafetyViolation("telemetry_stale", "telemetry is stale")
        if self.limits.max_temperature is not None and measurements.temperature is not None:
            if measurements.temperature >= self.limits.max_temperature:
                return SafetyViolation("temperature", "temperature limit exceeded")
        return None

    def _intent_violations(self, intent: ChargeIntent, state: SafetyContext) -> list[SafetyViolation]:
        violations: list[SafetyViolation] = []
        if state.allowed_next_stages is not None and intent.next_stage not in state.allowed_next_stages:
            violations.append(SafetyViolation("phase_transition", "next stage is not allowed"))
        if state.mix_authority_exhausted and (intent.next_stage or "").lower() == "mix":
            violations.append(SafetyViolation("mix_authority", "MIX authority is exhausted"))
        if intent.reason == "MIX_TIMEOUT":
            violations.append(SafetyViolation("mix_timeout", "MIX authority expired without an accepted hold"))
        if intent.completed and intent.target_voltage is None and intent.target_current is None:
            return violations
        if intent.target_voltage is None or intent.target_current is None:
            violations.append(SafetyViolation("intent", "active intent has incomplete targets"))
            return violations
        if intent.target_voltage <= 0 or intent.target_current <= 0:
            violations.append(SafetyViolation("intent", "targets must be positive"))
            return violations
        if intent.target_voltage > self.limits.max_voltage:
            violations.append(SafetyViolation("voltage", "configured voltage limit exceeded"))
        if intent.target_current > self.limits.max_current:
            violations.append(SafetyViolation("current", "configured current limit exceeded"))
        profile_limits = state.profile.limits if state.profile is not None else None
        if profile_limits is not None:
            if intent.target_voltage > profile_limits.max_voltage:
                violations.append(SafetyViolation("chemistry_voltage", "battery chemistry voltage envelope exceeded"))
            if intent.target_current > profile_limits.max_current:
                violations.append(SafetyViolation("chemistry_current", "battery chemistry current envelope exceeded"))
        if state.profile is not None and state.profile.recipe is None:
            violations.append(SafetyViolation("recipe", "battery profile has no validated recipe"))
        return violations

    def _accept(self, reason: str) -> SafetyDecision:
        return SafetyDecision(True, reason, (), self._limits())

    def _reject(self, first: SafetyViolation, violations: tuple[SafetyViolation, ...] = ()) -> SafetyDecision:
        reasons = {
            "telemetry": "TELEMETRY_INVALID",
            "ownership": "OWNERSHIP_NOT_ALLOWED",
            "strategy": "STRATEGY_UNAVAILABLE",
            "temperature": "TEMPERATURE_LIMIT",
            "telemetry_stale": "TELEMETRY_STALE",
        }
        return SafetyDecision(False, reasons.get(first.type, first.type.upper()), violations or (first,), self._limits())

    def _limits(self) -> Mapping[str, float]:
        limits = {"max_voltage": self.limits.max_voltage, "max_current": self.limits.max_current}
        if self.limits.max_temperature is not None:
            limits["max_temperature"] = self.limits.max_temperature
        if self.limits.telemetry_max_age_seconds is not None:
            limits["telemetry_max_age_seconds"] = self.limits.telemetry_max_age_seconds
        return limits
