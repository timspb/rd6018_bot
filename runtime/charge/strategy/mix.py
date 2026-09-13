"""Mix policy and regulation-specific CC/CV exit policies."""

from __future__ import annotations

from dataclasses import dataclass, field
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
class MixCurrentContainmentState:
    """State for the delayed CV-Mix current-setpoint containment."""

    enabled: bool = False
    activated_at: Optional[float] = None
    fixed_limit: Optional[float] = None
    last_recalculation: Optional[float] = None
    reduction_count: int = 0


@dataclass
class MixExitRuntimeState:
    phase: str = "unarmed"
    observed_vmax: Optional[float] = None
    observed_imin: Optional[float] = None
    confirmation_count: int = 0
    hold_started_at: Optional[float] = None
    containment: MixCurrentContainmentState = field(default_factory=MixCurrentContainmentState)


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
    containment_start_seconds: float = 30 * 60
    containment_recalc_seconds: float = 10 * 60
    containment_headroom_a: float = 0.4

    def __post_init__(self) -> None:
        if min(self.imin_current, self.delta_current, self.target_voltage, self.target_current) <= 0:
            raise ValueError("CV Mix recipe values must be positive")
        if (
            self.confirmations_required <= 0
            or self.hold_seconds < 0
            or self.confirmation_interval_seconds < 0
            or self.containment_start_seconds < 0
            or self.containment_recalc_seconds <= 0
            or self.containment_headroom_a < 0
        ):
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
            intent = self.cv.evaluate(measurements)
            return self._apply_cv_containment(intent, measurements)
        raise ValueError("Mix mode must be CC or CV")

    def _apply_cv_containment(self, intent: ChargeIntent, measurements: Measurements) -> ChargeIntent:
        """Cap the V3 CV Mix current intent without touching any actuator.

        The cap is anchored to confirmed Imin and therefore cannot follow a
        rising measured current.  It is eligible only after the configured
        elapsed Mix time and is refreshed on the configured cadence.  A
        refresh can only lower the already-issued domain setpoint.
        """
        if (
            intent.completed
            or
            intent.target_current is None
            or self.authority.started_at is None
            or measurements.time is None
            or self.cv.state.observed_imin is None
        ):
            return intent
        elapsed = measurements.time - self.authority.started_at
        if elapsed < self.cv.config.containment_start_seconds:
            return intent
        containment = self.cv.state.containment
        last = containment.last_recalculation
        if last is not None and measurements.time - last < self.cv.config.containment_recalc_seconds:
            if containment.fixed_limit is None:
                return intent
            return self._with_current(intent, containment.fixed_limit)

        candidate = self.cv.state.observed_imin + self.cv.config.delta_current + self.cv.config.containment_headroom_a
        candidate = min(candidate, self.cv.config.target_current)
        previous = containment.fixed_limit
        setpoint = candidate if previous is None else min(previous, candidate)
        if previous is not None and setpoint < previous:
            containment.reduction_count += 1
        containment.enabled = True
        containment.activated_at = containment.activated_at or measurements.time
        containment.fixed_limit = setpoint
        containment.last_recalculation = measurements.time
        return self._with_current(intent, setpoint)

    @staticmethod
    def _with_current(intent: ChargeIntent, current: float) -> ChargeIntent:
        return ChargeIntent(
            intent.target_voltage,
            current,
            intent.next_stage,
            intent.completed,
            intent.reason,
        )

    def _account_authority(self, measurements: Measurements) -> None:
        if self.authority.started_at is None and measurements.time is not None:
            self.authority.started_at = measurements.time
            self.authority.last_timestamp = measurements.time
        elif measurements.time is not None and self.authority.last_timestamp is not None:
            self.authority.active_seconds += max(0.0, measurements.time - self.authority.last_timestamp)
            self.authority.last_timestamp = measurements.time
        if self.authority.active_seconds >= self.config.active_authority_seconds:
            self.authority.exhausted = True
