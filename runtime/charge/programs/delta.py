"""Pure native Delta charge program."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..battery import BatteryProfile
from ..contracts.delta import DeltaState
from ..intent import ChargeIntent
from ..measurements import Measurements
from ..program import ChargeProgram
from ..state import ChargeState, DeltaRuntimeState


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

    @property
    def threshold_name(self) -> str:
        """Name of the configured gate, never the observed comparison value."""
        return "imin" if self.mode == "CV" else "vmax"


class DeltaProgram(ChargeProgram):
    """Evaluate Delta evidence and return intent without side effects."""

    def __init__(
        self,
        battery: BatteryProfile,
        config: DeltaConfig,
        runtime_state: Optional[DeltaRuntimeState] = None,
    ) -> None:
        self.battery = battery
        self.config = config
        self.runtime_state = runtime_state or DeltaRuntimeState()

    def evaluate(self, state: ChargeState, measurements: Measurements) -> ChargeIntent:
        # A caller may provide the owned continuity state on ChargeState; the
        # constructor-owned state remains a compatibility default for the
        # standalone domain service and tests.
        runtime = state.delta_state or self.runtime_state
        current_state = DeltaState(runtime.phase)
        if current_state == DeltaState.UNARMED:
            if measurements.voltage is None or measurements.current is None:
                return ChargeIntent(None, None, DeltaState.STOPPED.value, True, "DELTA_EVIDENCE_INVALID")
            if self.config.mode == "CC" and measurements.voltage >= self.config.reference:
                runtime.observed_vmax = measurements.voltage
                runtime.observed_reference_current = measurements.current
            elif self.config.mode == "CV" and measurements.current <= self.config.reference:
                runtime.observed_imin = measurements.current
            else:
                return self._intent(DeltaState.UNARMED, "DELTA_WAIT_EXTREMUM")
            runtime.phase = DeltaState.TRACKING.value
            return self._intent(DeltaState.TRACKING, "DELTA_ENTER")
        if current_state == DeltaState.TRACKING:
            if measurements.voltage is None or measurements.current is None:
                return ChargeIntent(None, None, DeltaState.STOPPED.value, True, "DELTA_EVIDENCE_INVALID")
            if self.config.mode == "CC":
                if runtime.observed_reference_current is None:
                    return ChargeIntent(None, None, DeltaState.STOPPED.value, True, "DELTA_EVIDENCE_INVALID")
                reached = measurements.current <= runtime.observed_reference_current - self.config.delta
            else:
                if runtime.observed_imin is None:
                    return ChargeIntent(None, None, DeltaState.STOPPED.value, True, "DELTA_EVIDENCE_INVALID")
                reached = measurements.current >= runtime.observed_imin + self.config.delta
            if reached:
                runtime.confirmation_count += 1
            if reached and runtime.confirmation_count >= self.config.confirmations_required:
                runtime.phase = DeltaState.CONFIRMED_HOLD.value
                runtime.hold_started = measurements.time
                return self._intent(DeltaState.CONFIRMED_HOLD, "DELTA_HOLD_START")
            return self._intent(DeltaState.TRACKING, "DELTA_HOLD_WAIT")
        if current_state == DeltaState.CONFIRMED_HOLD:
            hold_started = runtime.hold_started
            now = measurements.time
            if now is not None and hold_started is not None and now - hold_started >= self.config.hold_seconds:
                runtime.phase = DeltaState.COMPLETE.value
                return ChargeIntent(self.config.target_voltage, self.config.target_current, self.config.completed_stage, True, "DELTA_COMPLETE")
            return self._intent(DeltaState.CONFIRMED_HOLD, "DELTA_HOLD_RUNNING")
        return ChargeIntent(None, None, DeltaState.STOPPED.value, True, "DELTA_STOP")

    def _intent(self, stage: DeltaState, reason: str) -> ChargeIntent:
        return ChargeIntent(self.config.target_voltage, self.config.target_current, stage.value, False, reason)
