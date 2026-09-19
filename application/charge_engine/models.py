"""Data-only V3 charge engine contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class Phase(str, Enum):
    PREP = "PREP"
    MAIN = "MAIN"
    DESULFATION = "DESULFATION"
    MIX = "MIX"
    HOLD = "HOLD"
    SAFE_WAIT = "SAFE_WAIT"
    DONE = "DONE"


@dataclass(frozen=True)
class BatteryState:
    phase: Phase = Phase.PREP
    main_complete: bool = False
    desulfation_requested: bool = False
    desulfation_complete: bool = False
    delta_confirmed: bool = False
    hold_complete: bool = False
    safe_wait_complete: bool = False
    termination_requested: bool = False
    condition_values: Tuple[Tuple[str, bool], ...] = field(default_factory=tuple)

    def condition(self, key: str) -> bool:
        if key == "__entry__":
            return True
        values = dict(self.condition_values)
        if str(key) in values:
            return bool(values[str(key)])
        return bool(getattr(self, str(key), False))


@dataclass(frozen=True)
class TelemetrySnapshot:
    timestamp: float
    voltage_v: Optional[float]
    current_a: Optional[float]
    temperature_c: Optional[float]
    fresh: bool = True

    @property
    def complete(self) -> bool:
        return (
            self.fresh
            and self.voltage_v is not None
            and self.current_a is not None
            and self.temperature_c is not None
        )


@dataclass(frozen=True)
class ChargeDecision:
    current_phase: Phase
    desired_voltage_v: Optional[float]
    desired_current_a: Optional[float]
    reason: str
    conditions: Tuple[str, ...] = field(default_factory=tuple)
    next_transition_criteria: Tuple[str, ...] = field(default_factory=tuple)
    next_phase: Optional[Phase] = None
    program_id: str = ""
    confidence: str = "UNKNOWN"
    decision_id: str = ""

    @property
    def has_setpoints(self) -> bool:
        return self.desired_voltage_v is not None and self.desired_current_a is not None
