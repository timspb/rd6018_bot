from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, FrozenSet, Iterable, Optional


class SignalEvent(str, Enum):
    TELEMETRY_INVALID = "telemetry_invalid"
    CURRENT_MINIMUM_UPDATED = "current_minimum_updated"
    CURRENT_PLATEAU = "current_plateau"
    CURRENT_REVERSAL_CONFIRMED = "current_reversal_confirmed"
    VOLTAGE_MAXIMUM_UPDATED = "voltage_maximum_updated"
    VOLTAGE_REVERSAL_CONFIRMED = "voltage_reversal_confirmed"
    END_OF_CHARGE_LIKELY = "end_of_charge_likely"
    THERMAL_ACCELERATION = "thermal_acceleration"
    VOLTAGE_SAG_DURING_REVERSAL = "voltage_sag_during_reversal"


@dataclass(frozen=True)
class SignalSample:
    timestamp_s: float
    voltage_v: float
    current_a: float
    temp_c: float
    is_cv: bool = False
    is_cc: bool = False


@dataclass(frozen=True)
class SignalAnalyzerConfig:
    history_max_samples: int = 720
    rate_window_s: float = 15 * 60
    plateau_window_s: float = 15 * 60
    plateau_min_samples: int = 5

    # Absolute current terms below are instrumentation/noise floors, not Pb chemistry
    # limits. Battery-scale decisions belong in C-rate policy/audit layers.
    plateau_abs_span_a: float = 0.03
    plateau_rel_span: float = 0.05
    current_min_update_hysteresis_a: float = 0.005

    # CV: finish evidence is a rise of current from a real Imin.
    # The absolute term only prevents sub-resolution current noise from looking like
    # a meaningful reversal.
    reversal_ratio: float = 0.30
    reversal_abs_a: float = 0.03
    reversal_confirmations: int = 3
    reversal_confirmation_spacing_s: float = 50.0
    reversal_min_age_s: float = 120.0

    # CC: the controlled variable is current, so finish evidence must be expressed in
    # voltage. Track Vmax and confirm a real fall from that peak instead of trying to
    # infer CC completion from current, which is intentionally held approximately flat.
    voltage_max_update_hysteresis_v: float = 0.005
    voltage_reversal_abs_v: float = 0.03
    voltage_reversal_confirmations: int = 3
    voltage_reversal_confirmation_spacing_s: float = 50.0
    voltage_reversal_min_age_s: float = 120.0

    target_voltage_tolerance_v: float = 0.20
    voltage_sag_v: float = 0.15
    thermal_warn_c_per_min: float = 0.12
    # Measurement-rate floors, not battery-size chemistry thresholds.
    min_current_rise_for_thermal_a_per_min: float = 0.005
    min_voltage_fall_for_thermal_v_per_min: float = 0.005


@dataclass(frozen=True)
class SignalMetrics:
    d_voltage_v_per_min: Optional[float]
    d_current_a_per_min: Optional[float]
    d_temp_c_per_min: Optional[float]
    current_min_a: Optional[float]
    seconds_since_current_min: Optional[float]
    delta_current_from_min_a: Optional[float]
    reversal_threshold_a: Optional[float]
    current_plateau_span_a: Optional[float]
    current_plateau_center_a: Optional[float]
    reversal_confirmations: int
    # CC-specific voltage evidence. Defaults preserve compatibility with older test
    # fixtures that instantiate SignalMetrics directly.
    voltage_max_v: Optional[float] = None
    seconds_since_voltage_max: Optional[float] = None
    delta_voltage_from_max_v: Optional[float] = None
    voltage_reversal_threshold_v: Optional[float] = None
    voltage_reversal_confirmations: int = 0


@dataclass(frozen=True)
class SignalAnalysis:
    sample: SignalSample
    metrics: SignalMetrics
    events: FrozenSet[SignalEvent] = field(default_factory=frozenset)

    def has(self, event: SignalEvent) -> bool:
        return event in self.events


class SignalAnalyzer:
    """Extract slow Pb charge features from raw U/I/T telemetry.

    The analyzer deliberately does not decide which voltage a recipe may use.
    It only turns the trajectory into deterministic, testable evidence.

    Control-mode invariant:
    - CV: current is the response variable, so completion evidence is Imin -> dI rise;
    - CC: voltage is the response variable, so completion evidence is Vmax -> dV fall.

    Absolute A/V thresholds in this class represent observation resolution/noise
    floors. Chemistry and capacity-sensitive interpretation belongs later in the
    evidence/policy layer.
    """

    def __init__(self, config: Optional[SignalAnalyzerConfig] = None) -> None:
        self.config = config or SignalAnalyzerConfig()
        self._samples: Deque[SignalSample] = deque(
            maxlen=self.config.history_max_samples
        )
        self.stage_name: Optional[str] = None
        self.target_voltage_v: Optional[float] = None

        self._current_min_a: Optional[float] = None
        self._current_min_time_s: Optional[float] = None
        self._reversal_confirmations = 0
        self._last_reversal_confirmation_s: Optional[float] = None
        self._reversal_emitted = False

        self._voltage_max_v: Optional[float] = None
        self._voltage_max_time_s: Optional[float] = None
        self._voltage_reversal_confirmations = 0
        self._last_voltage_reversal_confirmation_s: Optional[float] = None
        self._voltage_reversal_emitted = False

    def reset_stage(
        self,
        stage_name: Optional[str],
        *,
        target_voltage_v: Optional[float] = None,
    ) -> None:
        self._samples.clear()
        self.stage_name = stage_name
        self.target_voltage_v = target_voltage_v

        self._current_min_a = None
        self._current_min_time_s = None
        self._reversal_confirmations = 0
        self._last_reversal_confirmation_s = None
        self._reversal_emitted = False

        self._voltage_max_v = None
        self._voltage_max_time_s = None
        self._voltage_reversal_confirmations = 0
        self._last_voltage_reversal_confirmation_s = None
        self._voltage_reversal_emitted = False

    @staticmethod
    def _valid_sample(sample: SignalSample) -> bool:
        values = (
            sample.timestamp_s,
            sample.voltage_v,
            sample.current_a,
            sample.temp_c,
        )
        if not all(math.isfinite(v) for v in values):
            return False
        if sample.timestamp_s < 0:
            return False
        if sample.voltage_v <= 0 or sample.voltage_v > 30:
            return False
        if sample.current_a < 0 or sample.current_a > 100:
            return False
        if sample.temp_c < -50 or sample.temp_c > 100:
            return False
        return True

    @staticmethod
    def _rate_per_min(samples: Iterable[SignalSample], attr: str) -> Optional[float]:
        items = list(samples)
        if len(items) < 2:
            return None
        first = items[0]
        last = items[-1]
        dt = last.timestamp_s - first.timestamp_s
        if dt <= 0:
            return None
        delta = float(getattr(last, attr)) - float(getattr(first, attr))
        return delta / dt * 60.0

    def _window(self, now_s: float, width_s: float) -> list[SignalSample]:
        floor = now_s - width_s
        return [s for s in self._samples if s.timestamp_s >= floor]

    def _plateau_metrics(self, now_s: float) -> tuple[Optional[float], Optional[float], bool]:
        window = [
            s
            for s in self._window(now_s, self.config.plateau_window_s)
            if s.is_cv
        ]
        if len(window) < self.config.plateau_min_samples:
            return None, None, False
        currents = [s.current_a for s in window]
        span = max(currents) - min(currents)
        center = statistics.median(currents)
        limit = max(
            self.config.plateau_abs_span_a,
            abs(center) * self.config.plateau_rel_span,
        )
        return span, center, span <= limit

    def _reversal_threshold_a(self) -> Optional[float]:
        if self._current_min_a is None:
            return None
        return max(
            self.config.reversal_abs_a,
            self._current_min_a * self.config.reversal_ratio,
        )

    def _voltage_reversal_threshold_v(self) -> Optional[float]:
        if self._voltage_max_v is None:
            return None
        return max(0.0, float(self.config.voltage_reversal_abs_v))

    def _empty_metrics(self) -> SignalMetrics:
        return SignalMetrics(
            d_voltage_v_per_min=None,
            d_current_a_per_min=None,
            d_temp_c_per_min=None,
            current_min_a=self._current_min_a,
            seconds_since_current_min=None,
            delta_current_from_min_a=None,
            reversal_threshold_a=self._reversal_threshold_a(),
            current_plateau_span_a=None,
            current_plateau_center_a=None,
            reversal_confirmations=self._reversal_confirmations,
            voltage_max_v=self._voltage_max_v,
            seconds_since_voltage_max=None,
            delta_voltage_from_max_v=None,
            voltage_reversal_threshold_v=self._voltage_reversal_threshold_v(),
            voltage_reversal_confirmations=self._voltage_reversal_confirmations,
        )

    def _update_minimum(self, sample: SignalSample, events: set[SignalEvent]) -> None:
        if not sample.is_cv:
            return
        hysteresis = max(0.0, float(self.config.current_min_update_hysteresis_a))
        if self._current_min_a is None or sample.current_a < self._current_min_a - hysteresis:
            self._current_min_a = sample.current_a
            self._current_min_time_s = sample.timestamp_s
            self._reversal_confirmations = 0
            self._last_reversal_confirmation_s = None
            self._reversal_emitted = False
            events.add(SignalEvent.CURRENT_MINIMUM_UPDATED)

    def _update_voltage_maximum(self, sample: SignalSample, events: set[SignalEvent]) -> None:
        if not sample.is_cc:
            return
        hysteresis = max(0.0, float(self.config.voltage_max_update_hysteresis_v))
        if self._voltage_max_v is None or sample.voltage_v > self._voltage_max_v + hysteresis:
            self._voltage_max_v = sample.voltage_v
            self._voltage_max_time_s = sample.timestamp_s
            self._voltage_reversal_confirmations = 0
            self._last_voltage_reversal_confirmation_s = None
            self._voltage_reversal_emitted = False
            events.add(SignalEvent.VOLTAGE_MAXIMUM_UPDATED)

    def _update_current_reversal(self, sample: SignalSample, events: set[SignalEvent]) -> None:
        if not sample.is_cv:
            return
        if self._current_min_a is None or self._current_min_time_s is None:
            return
        if sample.timestamp_s - self._current_min_time_s < self.config.reversal_min_age_s:
            return

        threshold = self._reversal_threshold_a()
        if threshold is None:
            return
        delta = sample.current_a - self._current_min_a
        qualifies = delta >= threshold

        if not qualifies:
            if delta < threshold * 0.5:
                self._reversal_confirmations = 0
                self._last_reversal_confirmation_s = None
            return

        if (
            self._last_reversal_confirmation_s is None
            or sample.timestamp_s - self._last_reversal_confirmation_s
            >= self.config.reversal_confirmation_spacing_s
        ):
            self._reversal_confirmations += 1
            self._last_reversal_confirmation_s = sample.timestamp_s

        if (
            self._reversal_confirmations >= self.config.reversal_confirmations
            and not self._reversal_emitted
        ):
            self._reversal_emitted = True
            events.add(SignalEvent.CURRENT_REVERSAL_CONFIRMED)

    # Backwards-compatible private alias used by older tests/instrumentation.
    def _update_reversal(self, sample: SignalSample, events: set[SignalEvent]) -> None:
        self._update_current_reversal(sample, events)

    def _update_voltage_reversal(self, sample: SignalSample, events: set[SignalEvent]) -> None:
        if not sample.is_cc:
            return
        if self._voltage_max_v is None or self._voltage_max_time_s is None:
            return
        if (
            sample.timestamp_s - self._voltage_max_time_s
            < self.config.voltage_reversal_min_age_s
        ):
            return

        threshold = self._voltage_reversal_threshold_v()
        if threshold is None:
            return
        delta = self._voltage_max_v - sample.voltage_v
        qualifies = delta >= threshold

        if not qualifies:
            if delta < threshold * 0.5:
                self._voltage_reversal_confirmations = 0
                self._last_voltage_reversal_confirmation_s = None
            return

        if (
            self._last_voltage_reversal_confirmation_s is None
            or sample.timestamp_s - self._last_voltage_reversal_confirmation_s
            >= self.config.voltage_reversal_confirmation_spacing_s
        ):
            self._voltage_reversal_confirmations += 1
            self._last_voltage_reversal_confirmation_s = sample.timestamp_s

        if (
            self._voltage_reversal_confirmations >= self.config.voltage_reversal_confirmations
            and not self._voltage_reversal_emitted
        ):
            self._voltage_reversal_emitted = True
            events.add(SignalEvent.VOLTAGE_REVERSAL_CONFIRMED)

    def observe(self, sample: SignalSample) -> SignalAnalysis:
        if not self._valid_sample(sample):
            return SignalAnalysis(
                sample=sample,
                metrics=self._empty_metrics(),
                events=frozenset({SignalEvent.TELEMETRY_INVALID}),
            )

        if self._samples and sample.timestamp_s <= self._samples[-1].timestamp_s:
            return SignalAnalysis(
                sample=sample,
                metrics=self._empty_metrics(),
                events=frozenset({SignalEvent.TELEMETRY_INVALID}),
            )

        self._samples.append(sample)
        events: set[SignalEvent] = set()
        self._update_minimum(sample, events)
        self._update_voltage_maximum(sample, events)

        rate_window = self._window(sample.timestamp_s, self.config.rate_window_s)
        du = self._rate_per_min(rate_window, "voltage_v")
        di = self._rate_per_min(rate_window, "current_a")
        dt = self._rate_per_min(rate_window, "temp_c")

        plateau_span, plateau_center, is_plateau = self._plateau_metrics(sample.timestamp_s)
        if is_plateau:
            events.add(SignalEvent.CURRENT_PLATEAU)

        self._update_current_reversal(sample, events)
        self._update_voltage_reversal(sample, events)

        seconds_since_min = (
            sample.timestamp_s - self._current_min_time_s
            if self._current_min_time_s is not None
            else None
        )
        delta_from_min = (
            sample.current_a - self._current_min_a
            if self._current_min_a is not None
            else None
        )
        seconds_since_vmax = (
            sample.timestamp_s - self._voltage_max_time_s
            if self._voltage_max_time_s is not None
            else None
        )
        delta_from_vmax = (
            self._voltage_max_v - sample.voltage_v
            if self._voltage_max_v is not None
            else None
        )

        cv_thermal_acceleration = (
            sample.is_cv
            and dt is not None
            and di is not None
            and dt >= self.config.thermal_warn_c_per_min
            and di >= self.config.min_current_rise_for_thermal_a_per_min
        )
        cc_thermal_acceleration = (
            sample.is_cc
            and dt is not None
            and du is not None
            and dt >= self.config.thermal_warn_c_per_min
            and du <= -self.config.min_voltage_fall_for_thermal_v_per_min
        )
        thermal_acceleration = cv_thermal_acceleration or cc_thermal_acceleration
        if thermal_acceleration:
            events.add(SignalEvent.THERMAL_ACCELERATION)

        current_reversal_now = (
            SignalEvent.CURRENT_REVERSAL_CONFIRMED in events or self._reversal_emitted
        )
        voltage_reversal_now = (
            SignalEvent.VOLTAGE_REVERSAL_CONFIRMED in events
            or self._voltage_reversal_emitted
        )

        # In CV, a current rise plus failure to hold the requested voltage is a bad
        # correlation and must not be mistaken for a healthy end-of-charge reversal.
        voltage_sag = (
            current_reversal_now
            and sample.is_cv
            and self.target_voltage_v is not None
            and sample.voltage_v
            < self.target_voltage_v - self.config.voltage_sag_v
        )
        if voltage_sag:
            events.add(SignalEvent.VOLTAGE_SAG_DURING_REVERSAL)

        near_target = (
            self.target_voltage_v is None
            or abs(sample.voltage_v - self.target_voltage_v)
            <= self.config.target_voltage_tolerance_v
        )
        cv_end = (
            current_reversal_now
            and sample.is_cv
            and near_target
            and not thermal_acceleration
            and not voltage_sag
        )
        # In CC the voltage setpoint is not the controlled quantity: the supply is
        # current-limited by definition. Therefore Vmax -> dV is itself the response
        # evidence and must not be gated by closeness to target_voltage_v.
        cc_end = (
            voltage_reversal_now
            and sample.is_cc
            and not thermal_acceleration
        )
        if cv_end or cc_end:
            events.add(SignalEvent.END_OF_CHARGE_LIKELY)

        return SignalAnalysis(
            sample=sample,
            metrics=SignalMetrics(
                d_voltage_v_per_min=du,
                d_current_a_per_min=di,
                d_temp_c_per_min=dt,
                current_min_a=self._current_min_a,
                seconds_since_current_min=seconds_since_min,
                delta_current_from_min_a=delta_from_min,
                reversal_threshold_a=self._reversal_threshold_a(),
                current_plateau_span_a=plateau_span,
                current_plateau_center_a=plateau_center,
                reversal_confirmations=self._reversal_confirmations,
                voltage_max_v=self._voltage_max_v,
                seconds_since_voltage_max=seconds_since_vmax,
                delta_voltage_from_max_v=delta_from_vmax,
                voltage_reversal_threshold_v=self._voltage_reversal_threshold_v(),
                voltage_reversal_confirmations=self._voltage_reversal_confirmations,
            ),
            events=frozenset(events),
        )
