"""Pure battery profile data model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .chemistry import ChemistryProfile
from .limits import ChargeLimits


@dataclass(frozen=True)
class BatteryProfile:
    """Identity and declared limits of one physical battery profile."""

    chemistry: ChemistryProfile
    capacity_ah: float
    manufacturer: Optional[str] = None
    nominal_voltage: float = 12.0
    limits: Optional[ChargeLimits] = None

    def __post_init__(self) -> None:
        if not isinstance(self.chemistry, ChemistryProfile):
            raise TypeError("chemistry must be a ChemistryProfile")
        if self.capacity_ah <= 0:
            raise ValueError("capacity must be positive")
        if self.nominal_voltage <= 0:
            raise ValueError("nominal voltage must be positive")
        if self.limits is not None and not isinstance(self.limits, ChargeLimits):
            raise TypeError("limits must be ChargeLimits or None")

