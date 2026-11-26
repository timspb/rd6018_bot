"""Pure native Manual charge program."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..battery import BatteryProfile
from ..intent import ChargeIntent
from ..measurements import Measurements
from ..program import ChargeProgram
from ..state import ChargeState


def manual_stop_threshold_reason(
    stop, *, active_elapsed_s: float, voltage: float, current: float
) -> Optional[str]:
    """Return the first configured Manual stop threshold that has been reached."""
    if stop.max_active_seconds is not None and active_elapsed_s >= stop.max_active_seconds:
        return "manual_time_limit"
    if stop.voltage_ge_v is not None and voltage >= stop.voltage_ge_v:
        return "manual_voltage_ge"
    if stop.voltage_le_v is not None and voltage <= stop.voltage_le_v:
        return "manual_voltage_le"
    if stop.current_ge_a is not None and current >= stop.current_ge_a:
        return "manual_current_ge"
    if stop.current_le_a is not None and current <= stop.current_le_a:
        return "manual_current_le"
    return None


def manual_main_tail_reached(
    *, imin: Optional[float], current_a: float, threshold_a: float
) -> bool:
    """Return whether the existing profile-less Manual MAIN CV tail rule is reached."""
    return imin is None or current_a <= threshold_a


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
