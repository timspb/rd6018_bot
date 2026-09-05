from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class BatteryChemistry(str, Enum):
    """Physical battery family. This is deliberately separate from a charge recipe."""

    AGM = "agm"
    EFB = "efb"
    CA_CA = "ca_ca"
    FLOODED = "flooded"
    CUSTOM = "custom"


class ChargeIntent(str, Enum):
    """Why the controller is charging the battery."""

    NORMAL = "normal"
    RECOVERY = "recovery"
    CONDITIONING = "conditioning"
    DIAGNOSTIC = "diagnostic"


class BatteryCondition(str, Enum):
    """Observed/declared battery condition, not a chemistry label."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    SULFATED_SUSPECTED = "sulfated_suspected"
    DRY_SUSPECTED = "dry_suspected"
    REHYDRATED = "rehydrated"
    OVERWET_SUSPECTED = "overwet_suspected"
    STRATIFIED_SUSPECTED = "stratified_suspected"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class BatteryIdentity:
    battery_id: str
    chemistry: BatteryChemistry
    nominal_capacity_ah: float
    manufacturer: str = ""
    model: str = ""

    def __post_init__(self) -> None:
        if not self.battery_id.strip():
            raise ValueError("battery_id must not be empty")
        if self.nominal_capacity_ah <= 0:
            raise ValueError("nominal_capacity_ah must be > 0")


@dataclass
class BatteryLifecycle:
    """Longitudinal state that survives individual charge sessions."""

    condition: BatteryCondition = BatteryCondition.UNKNOWN
    water_added_total_ml: float = 0.0
    water_added_per_cell_ml: Optional[float] = None
    refill_timestamp: Optional[float] = None
    cycles_since_refill: Optional[int] = None
    measured_capacity_ah: Optional[float] = None
    cca_a: Optional[float] = None
    internal_resistance_mohm: Optional[float] = None

    def mark_refill(
        self,
        *,
        total_ml: float,
        per_cell_ml: Optional[float] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        if total_ml < 0:
            raise ValueError("total_ml must be >= 0")
        if per_cell_ml is not None and per_cell_ml < 0:
            raise ValueError("per_cell_ml must be >= 0")
        self.condition = BatteryCondition.REHYDRATED
        self.water_added_total_ml += float(total_ml)
        self.water_added_per_cell_ml = (
            float(per_cell_ml) if per_cell_ml is not None else None
        )
        self.refill_timestamp = timestamp
        self.cycles_since_refill = 0

    def record_completed_cycle(self) -> None:
        if self.cycles_since_refill is not None:
            self.cycles_since_refill += 1


@dataclass(frozen=True)
class ChargeContext:
    identity: BatteryIdentity
    intent: ChargeIntent = ChargeIntent.NORMAL
    condition: BatteryCondition = BatteryCondition.UNKNOWN

    @property
    def is_recovery(self) -> bool:
        return self.intent in {ChargeIntent.RECOVERY, ChargeIntent.CONDITIONING}
