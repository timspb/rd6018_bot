"""Pure battery charge-limit data model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChargeLimits:
    """Declared envelope for a battery profile, not an actuator policy."""

    max_voltage: float
    absorption_voltage: float
    float_voltage: float
    max_current: float
    temperature_compensation_mv_per_c: Optional[float] = None
    compensation_reference_c: Optional[float] = None

    def __post_init__(self) -> None:
        if self.max_voltage <= 0 or self.absorption_voltage <= 0 or self.float_voltage <= 0:
            raise ValueError("charge voltages must be positive")
        if self.max_current <= 0:
            raise ValueError("max current must be positive")
        if self.absorption_voltage > self.max_voltage:
            raise ValueError("absorption voltage cannot exceed max voltage")
        if self.float_voltage > self.absorption_voltage:
            raise ValueError("float voltage cannot exceed absorption voltage")
        if self.temperature_compensation_mv_per_c is not None and self.compensation_reference_c is None:
            raise ValueError("temperature compensation requires a reference temperature")

