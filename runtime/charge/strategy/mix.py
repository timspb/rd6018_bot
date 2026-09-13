"""Mix policy and regulation-specific CC/CV exit policies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..intent import ChargeIntent
from ..measurements import Measurements


@dataclass
class MixAuthorityState:
    active_seconds: float = 0.0
    session_id: str | None = None
    exhausted: bool = False
    started_at: float | None = None
    last_timestamp: float | None = None


@dataclass
class MixExitRuntimeState:
    phase: str = "unarmed"
    observed_vmax: Optional[float] = None
    observed_imin: Optional[float] = None
    confirmation_count: int = 0
    hold_started_at: Optional[float] = None


@dataclass(frozen=True)
class CCMixExitConfig:
    vmax_voltage: float
    delta_voltage: float
    confirmations_required: int
    hold_seconds: float
    target_voltage: float
    target_current: float
    active_stage: str = "mix"
    hold_stage: str = "mix_hold"
    completed_stage: str = "done"
    confirmation_interval_seconds: float = 0.0

    def __post_init__(self) -> None:
        if min(self.vmax_voltage, self.delta_voltage, self.target_voltage, self.target_current) <= 0:
            raise ValueError("CC Mix recipe values must be positive")
        if self.confirmations_required <= 0 or self.hold_seconds < 0 or self.confirmation_interval_seconds < 0:
            raise ValueError("CC Mix timing configuration is invalid")


@dataclass(frozen=True)
class CVMixExitConfig:
    imin_current: float
    delta_current: float
    confirmations_required: int
    hold_seconds: float
    target_voltage: float
    target_current: float
    active_stage: str = "mix"
    hold_stage: str = "mix_hold"
    completed_stage: str = "done"
    confirmation_interval_seconds: float = 0.0

    def __post_init__(self) -> None:
        if min(self.imin_current, self.delta_current, self.target_voltage, self.target_current) <= 0:
            raise ValueError("CV Mix recipe values must be positive")
        if self.confirmations_required <= 0 or self.hold_seconds < 0 or self.confirmation_interval_seconds < 0:
            raise ValueError("CV Mix timing configuration is invalid")


class CCMixExitPolicy:
    def __init__(self, config: CCMixExitConfig, state: MixExitRuntimeState | None = None) -> None:
        self.config, self.state = config, state or MixExitRuntimeState()

    def evaluate(self, measurements: Measurements) -> ChargeIntent:
        if measurements.voltage is None or measurements.current is None:
            return ChargeIntent(None, None, "stopped", True, "MIX_CC_EVIDENCE_INVALID")
        if self.state.phase == "unarmed":
            if measurements.voltage < self.config.vmax_voltage:
                return self._active("MIX_CC_WAIT_VMAX")
            self.state.observed_vmax = measurements.voltage
            self.state.phase = "tracking"
            return self._active("MIX_CC_VMAX_CONFIRMED")
        if self.state.phase == "tracking":
            if self.state.observed_vmax is not None and measurements.voltage <= self.state.observed_vmax - self.config.delta_voltage:
                self.state.confirmation_count += 1
            if self.state.confirmation_count >= self.config.confirmations_required:
                self.state.phase = "hold"
                self.state.hold_started_at = measurements.time
                return self._active("MIX_CC_DELTA_CONFIRMED")
            return self._active("MIX_CC_DELTA_WAIT")
        if self.state.phase == "hold":
            if measurements.time is not None and self.state.hold_started_at is not None and measurements.time - self.state.hold_started_at >= self.config.hold_seconds:
                self.state.phase = "complete"
                return ChargeIntent(self.config.target_voltage, self.config.target_current, self.config.completed_stage, True, "MIX_CC_HOLD_COMPLETE")
            return self._active("MIX_CC_HOLD")
        return ChargeIntent(None, None, "stopped", True, "MIX_CC_STOP")

    def _active(self, reason: str) -> ChargeIntent:
        return ChargeIntent(self.config.target_voltage, self.config.target_current, self.config.active_stage, False, reason)


class CVMixExitPolicy:
    def __init__(self, config: CVMixExitConfig, state: MixExitRuntimeState | None = None) -> None:
        self.config, self.state = config, state or MixExitRuntimeState()

    def evaluate(self, measurements: Measurements) -> ChargeIntent:
        if measurements.voltage is None or measurements.current is None:
            return ChargeIntent(None, None, "stopped", True, "MIX_CV_EVIDENCE_INVALID")
        if self.state.phase == "unarmed":
            if measurements.current > self.config.imin_current:
                return self._active("MIX_CV_WAIT_IMIN")
            self.state.observed_imin = measurements.current
            self.state.phase = "tracking"
            return self._active("MIX_CV_IMIN_CONFIRMED")
        if self.state.phase == "tracking":
            if self.state.observed_imin is not None and measurements.current >= self.state.observed_imin + self.config.delta_current:
                self.state.confirmation_count += 1
            if self.state.confirmation_count >= self.config.confirmations_required:
                self.state.phase = "hold"
                self.state.hold_started_at = measurements.time
                return self._active("MIX_CV_DELTA_CONFIRMED")
            return self._active("MIX_CV_DELTA_WAIT")
        if self.state.phase == "hold":
            if measurements.time is not None and self.state.hold_started_at is not None and measurements.time - self.state.hold_started_at >= self.config.hold_seconds:
                self.state.phase = "complete"
                return ChargeIntent(self.config.target_voltage, self.config.target_current, self.config.completed_stage, True, "MIX_CV_HOLD_COMPLETE")
            return self._active("MIX_CV_HOLD")
        return ChargeIntent(None, None, "stopped", True, "MIX_CV_STOP")

    def _active(self, reason: str) -> ChargeIntent:
        return ChargeIntent(self.config.target_voltage, self.config.target_current, self.config.active_stage, False, reason)


@dataclass(frozen=True)
class MixPolicyConfig:
    active_authority_seconds: float
    cc: CCMixExitConfig
    cv: CVMixExitConfig
    session_id: str | None = None

    def __post_init__(self) -> None:
        if self.active_authority_seconds < 0:
            raise ValueError("Mix active authority duration must not be negative")


class MixPolicy:
    def __init__(self, config: MixPolicyConfig, authority: MixAuthorityState | None = None) -> None:
        self.config = config
        self.cc = CCMixExitPolicy(config.cc)
        self.cv = CVMixExitPolicy(config.cv)
        self.authority = authority or MixAuthorityState(session_id=config.session_id)

    def evaluate(self, mode: str, measurements: Measurements) -> ChargeIntent:
        self._account_authority(measurements)
        if self.authority.exhausted:
            return ChargeIntent(None, None, "stopped", True, "MIX_TIMEOUT")
        if mode == "CC":
            return self.cc.evaluate(measurements)
        if mode == "CV":
            return self.cv.evaluate(measurements)
        raise ValueError("Mix mode must be CC or CV")

    def _account_authority(self, measurements: Measurements) -> None:
        if self.authority.started_at is None and measurements.time is not None:
            self.authority.started_at = measurements.time
            self.authority.last_timestamp = measurements.time
        elif measurements.time is not None and self.authority.last_timestamp is not None:
            self.authority.active_seconds += max(0.0, measurements.time - self.authority.last_timestamp)
            self.authority.last_timestamp = measurements.time
        if self.authority.active_seconds >= self.config.active_authority_seconds:
            self.authority.exhausted = True
