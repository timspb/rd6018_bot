"""Fail-closed compatibility checks before execution policy/gate."""

from __future__ import annotations

from .models import (
    BatterySafetyEnvelope, EnvelopeEvidence, EnvelopeValidationResult,
    EnvelopeValidationStatus, HardwareSafetyEnvelope,
)
from .rules import power_within, within


class EnvelopeValidator:
    def validate(self, battery: BatterySafetyEnvelope, hardware: HardwareSafetyEnvelope,
                 *, requested_voltage: float | None = None, requested_current: float | None = None,
                 mode: str | None = None, profile: str | None = None) -> EnvelopeValidationResult:
        violations = []
        reasons = []
        if requested_voltage is not None:
            if requested_voltage > battery.max_charge_voltage:
                violations.append("battery_max_voltage")
            if not within(requested_voltage, hardware.min_voltage, hardware.max_voltage):
                violations.append("hardware_voltage_envelope")
        if requested_current is not None:
            if requested_current > battery.max_charge_current:
                violations.append("battery_max_current")
            if not within(requested_current, hardware.capabilities.min_current, min(hardware.max_current, hardware.capabilities.max_current)):
                violations.append("hardware_current_envelope")
        if not power_within(requested_voltage, requested_current, hardware.max_power):
            violations.append("hardware_max_power")
        if battery.chemistry not in hardware.supported_chemistry:
            violations.append("chemistry_not_supported")
        if mode is not None and mode not in hardware.supported_modes:
            violations.append("mode_not_supported")
        if profile is not None and battery.allowed_profiles and profile not in battery.allowed_profiles:
            violations.append("profile_not_allowed")
        if violations:
            reasons.append("requested execution is outside the declared envelope")
        status = EnvelopeValidationStatus.BLOCKED if violations else EnvelopeValidationStatus.ALLOWED
        evidence = EnvelopeEvidence(hardware, battery, requested_voltage, requested_current, mode, status)
        return EnvelopeValidationResult(status, tuple(reasons), tuple(violations), evidence)

