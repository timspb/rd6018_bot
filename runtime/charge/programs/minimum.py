"""Pure native Minimum charge program."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..battery import BatteryProfile
from ..intent import ChargeIntent
from ..measurements import Measurements
from ..program import ChargeProgram
from ..state import ChargeState


@dataclass(frozen=True)
class MinimumConfig:
    """Explicit program inputs; safety envelope remains outside the program."""

    target_voltage: float
    target_current: float
    completion_current: float
    completion_voltage: Optional[float] = None
    active_stage: str = "minimum"
    completed_stage: str = "delta"
    active_reason: str = "MINIMUM_ACTIVE"
    completion_reason: str = "MINIMUM_COMPLETE"

    def __post_init__(self) -> None:
        if self.target_voltage <= 0 or self.target_current <= 0 or self.completion_current < 0:
            raise ValueError("minimum targets and completion current are invalid")
        if self.completion_voltage is not None and self.completion_voltage <= 0:
            raise ValueError("completion voltage must be positive")
        if not self.active_stage or not self.completed_stage:
            raise ValueError("minimum stages must be non-empty")


class MinimumProgram(ChargeProgram):
    """Produce Minimum intent and transition when configured evidence is met."""

    def __init__(self, battery: BatteryProfile, config: MinimumConfig) -> None:
        self.battery = battery
        self.config = config

    def evaluate(self, state: ChargeState, measurements: Measurements) -> ChargeIntent:
        current_complete = (
            measurements.current is not None
            and measurements.current <= self.config.completion_current
        )
        voltage_complete = (
            self.config.completion_voltage is None
            or (
                measurements.voltage is not None
                and measurements.voltage >= self.config.completion_voltage
            )
        )
        complete = current_complete and voltage_complete
        return ChargeIntent(
            target_voltage=self.config.target_voltage,
            target_current=self.config.target_current,
            next_stage=self.config.completed_stage if complete else self.config.active_stage,
            completed=complete,
            reason=self.config.completion_reason if complete else self.config.active_reason,
        )
