"""Pure native Manual charge program."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..battery import BatteryProfile
from ..intent import ChargeIntent
from ..measurements import Measurements
from ..program import ChargeProgram
from ..state import ChargeState


@dataclass(frozen=True)
class ManualTargets:
    """Domain input supplied by an operator-facing boundary."""

    voltage: float
    current: float
    next_stage: Optional[str] = None
    reason: str = "manual targets"

    def __post_init__(self) -> None:
        if self.voltage <= 0 or self.current <= 0:
            raise ValueError("manual targets must be positive")


class ManualProgram(ChargeProgram):
    """Map declared manual targets to an intent without physical side effects."""

    def __init__(self, battery: BatteryProfile, targets: ManualTargets) -> None:
        self.battery = battery
        self.targets = targets

    def evaluate(self, state: ChargeState, measurements: Measurements) -> ChargeIntent:
        return ChargeIntent(
            target_voltage=self.targets.voltage,
            target_current=self.targets.current,
            next_stage=self.targets.next_stage or state.stage or "manual",
            completed=False,
            reason=self.targets.reason,
        )
