"""Data-only hardware and battery execution envelopes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from runtime.charge.chemistry import ChemistryProfile
from runtime.output.bridge.capabilities import HardwareCapability


class EnvelopeValidationStatus(str, Enum):
    ALLOWED = "ALLOWED"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class HardwareSafetyEnvelope:
    min_voltage: float
    max_voltage: float
    max_current: float
    max_power: float
    supported_modes: tuple[str, ...]
    supported_chemistry: tuple[ChemistryProfile, ...]
    capabilities: HardwareCapability

    def __post_init__(self) -> None:
        if self.min_voltage <= 0 or self.max_voltage < self.min_voltage:
            raise ValueError("invalid hardware voltage envelope")
        if self.max_current <= 0 or self.max_power <= 0:
            raise ValueError("invalid hardware current/power envelope")


@dataclass(frozen=True)
class BatterySafetyEnvelope:
    chemistry: ChemistryProfile
    nominal_voltage: float
    capacity_range: tuple[float, float]
    max_charge_voltage: float
    max_charge_current: float
    allowed_profiles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.nominal_voltage <= 0 or self.max_charge_voltage <= 0 or self.max_charge_current <= 0:
            raise ValueError("invalid battery envelope limits")
        if len(self.capacity_range) != 2 or not (0 < self.capacity_range[0] <= self.capacity_range[1]):
            raise ValueError("invalid battery capacity range")


@dataclass(frozen=True)
class EnvelopeEvidence:
    hardware: HardwareSafetyEnvelope
    battery: BatterySafetyEnvelope
    requested_voltage: float | None
    requested_current: float | None
    mode: str | None
    result: EnvelopeValidationStatus


@dataclass(frozen=True)
class EnvelopeValidationResult:
    status: EnvelopeValidationStatus
    reasons: tuple[str, ...] = ()
    violated_limits: tuple[str, ...] = ()
    evidence: EnvelopeEvidence | None = None
    confidence: str = "high"

    @property
    def allowed(self) -> bool:
        return self.status is not EnvelopeValidationStatus.BLOCKED

