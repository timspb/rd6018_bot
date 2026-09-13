"""Pure native Delta charge program."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..battery import BatteryProfile
from ..contracts.delta import DeltaState
from ..intent import ChargeIntent
from ..measurements import Measurements
from ..program import ChargeProgram
from ..state import ChargeState


@dataclass(frozen=True)
class DeltaConfig:
    target_voltage: float
    target_current: float
    mode: str
    reference: float
    delta: float
    confirmations_required: int = 3
    hold_seconds: float = 2 * 60 * 60
    tracking_stage: str = "delta"
    hold_stage: str = "delta_hold"
    completed_stage: str = "done"

    def __post_init__(self) -> None:
        if self.target_voltage <= 0 or self.target_current <= 0:
            raise ValueError("Delta targets must be positive")
        if self.mode not in {"CV", "CC"}:
            raise ValueError("Delta mode must be CV or CC")
        if self.reference <= 0 or self.delta <= 0:
            raise ValueError("Delta reference and delta must be positive")
        if self.confirmations_required <= 0 or self.hold_seconds < 0:
            raise ValueError("Delta confirmation/hold configuration is invalid")


class DeltaProgram(ChargeProgram):
    """Evaluate Delta evidence and return intent without side effects."""

    def __init__(self, battery: BatteryProfile, config: DeltaConfig) -> None:
        self.battery = battery
        self.config = config

    def evaluate(self, state: ChargeState, measurements: Measurements) -> ChargeIntent:
        current_state = state.stage or DeltaState.UNARMED.value
        if current_state == DeltaState.UNARMED.value:
            return self._intent(DeltaState.TRACKING, "DELTA_ENTER")
        if current_state == DeltaState.TRACKING.value:
            if measurements.voltage is None or measurements.current is None:
                return ChargeIntent(None, None, DeltaState.STOPPED.value, True, "DELTA_EVIDENCE_INVALID")
            reversal = (
                measurements.current <= self.config.reference - self.config.delta
                if self.config.mode == "CV"
                else measurements.voltage <= self.config.reference - self.config.delta
            )
            confirmations = int(state.timers.get("delta_confirmations", 0))
            if reversal and confirmations + 1 >= self.config.confirmations_required:
                return self._intent(DeltaState.CONFIRMED_HOLD, "DELTA_HOLD_START")
            return self._intent(DeltaState.TRACKING, "DELTA_HOLD_WAIT")
        if current_state == DeltaState.CONFIRMED_HOLD.value:
            hold_started = state.timers.get("delta_hold_started", 0.0)
            now = measurements.time
            if now is not None and hold_started > 0 and now - hold_started >= self.config.hold_seconds:
                return ChargeIntent(self.config.target_voltage, self.config.target_current, self.config.completed_stage, True, "DELTA_COMPLETE")
            return self._intent(DeltaState.CONFIRMED_HOLD, "DELTA_HOLD_RUNNING")
        return ChargeIntent(None, None, DeltaState.STOPPED.value, True, "DELTA_STOP")

    def _intent(self, stage: DeltaState, reason: str) -> ChargeIntent:
        return ChargeIntent(self.config.target_voltage, self.config.target_current, stage.value, False, reason)
