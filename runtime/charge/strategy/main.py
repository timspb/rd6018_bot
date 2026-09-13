"""Main-stage policy; all tunables are supplied by MainPolicyConfig."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..intent import ChargeIntent
from ..measurements import Measurements


@dataclass(frozen=True)
class MainPolicyConfig:
    target_voltage: float
    target_current: float
    tail_current: float
    tail_hold_seconds: float
    plateau_current: float
    plateau_hold_seconds: float
    main_stage: str = "main"
    recovery_stage: str = "recovery"
    mix_stage: str = "mix"
    done_stage: str = "done"

    def __post_init__(self) -> None:
        if min(self.target_voltage, self.target_current, self.tail_current, self.plateau_current) <= 0:
            raise ValueError("main recipe values must be positive")
        if min(self.tail_hold_seconds, self.plateau_hold_seconds) < 0:
            raise ValueError("main recipe durations must not be negative")


class MainPolicy:
    """Select normal tail, recovery, or Mix; never evaluates Delta completion."""

    def __init__(self, config: MainPolicyConfig) -> None:
        self.config = config

    def evaluate(self, state, measurements: Measurements, recovery_policy) -> ChargeIntent:
        if measurements.voltage is None or measurements.current is None:
            return ChargeIntent(None, None, "stopped", True, "MAIN_EVIDENCE_INVALID")
        now = measurements.time
        if measurements.current <= self.config.tail_current:
            if state.tail_started_at is None:
                state.tail_started_at = now
            if now is not None and state.tail_started_at is not None and now - state.tail_started_at >= self.config.tail_hold_seconds:
                return ChargeIntent(self.config.target_voltage, self.config.target_current, self.config.done_stage, True, "MAIN_TAIL_COMPLETE")
            return self._active("MAIN_TAIL_HOLD")
        state.tail_started_at = None

        if measurements.voltage >= self.config.target_voltage and measurements.current >= self.config.plateau_current:
            if state.plateau_started_at is None:
                state.plateau_started_at = now
            if now is not None and state.plateau_started_at is not None and now - state.plateau_started_at >= self.config.plateau_hold_seconds:
                state.plateau_started_at = None
                return recovery_policy.on_plateau(self.config.target_voltage, self.config.target_current)
        else:
            state.plateau_started_at = None
        return self._active("MAIN_ACTIVE")

    def _active(self, reason: str) -> ChargeIntent:
        return ChargeIntent(self.config.target_voltage, self.config.target_current, self.config.main_stage, False, reason)
