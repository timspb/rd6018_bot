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


@dataclass(frozen=True)
class SignalAnalyzerConfig:
    history_max_samples: int = 720
    rate_window_s: float = 15 * 60
    plateau_window_s: float = 15 * 60
    plateau_min_samples: int = 5
    plateau_abs_span_a: float = 0.03
    plateau_rel_span: float = 0.05
    reversal_ratio: float = 0.30
    reversal_abs_a: float = 0.03
    reversal_confirmations: int = 3
    reversal_confirmation_spacing_s: float = 50.0
    reversal_min_age_s: float = 120.0
    target_voltage_tolerance_v: float = 0.20
    voltage_sag_v: float = 0.15
    thermal_warn_c_per_min: float = 0.12
    min_current_rise_for_thermal_a_per_min: float = 0.005


@dataclass(frozen=True)
class SignalMetrics:
    d_voltage_v_per_min: Optional[float]
    d_current_a_per_min: Optional[float]
    d_temp_c_per_min: Optional[float]
    current_min_a: Optional[float]
    seconds_since_current_min: Optional[float]
    delta_current_from_min_a: Optional[float]
    current_plateau_span_a: Optional[float]
    current_plateau_center_a: Optional[float]
    reversal_confirmations: int


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

    def _update_minimum(self, sample: SignalSample, events: set[SignalEvent]) -> None:
        if not sample.is_cv:
            return
        if self._current_min_a is None or sample.current_a < self._current_min_a - 0.005:
            self._current_min_a = sample.current_a
            self._current_min_time_s = sample.timestamp_s
            self._reversal_confirmations = 0
            self._last_reversal_confirmation_s = None
            self._reversal_emitted = False
            events.add(SignalEvent.CURRENT_MINIMUM_UPDATED)

    def _update_reversal(self, sample: SignalSample, events: set[SignalEvent]) -> None:
        if not sample.is_cv:
            return
        if self._current_min_a is None or self._current_min_time_s is None:
            return
        if sample.timestamp_s - self._current_min_time_s < self.config.reversal_min_age_s:
            return

        threshold = max(
            self.config.reversal_abs_a,
            self._current_min_a * self.config.reversal_ratio,
        )
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

    def observe(self, sample: SignalSample) -> SignalAnalysis:
        if not self._valid_sample(sample):
            return SignalAnalysis(
                sample=sample,
                metrics=SignalMetrics(
                    d_voltage_v_per_min=None,
                    d_current_a_per_min=None,
                    d_temp_c_per_min=None,
                    current_min_a=self._current_min_a,
                    seconds_since_current_min=None,
                    delta_current_from_min_a=None,
                    current_plateau_span_a=None,
                    current_plateau_center_a=None,
                    reversal_confirmations=self._reversal_confirmations,
                ),
                events=frozenset({SignalEvent.TELEMETRY_INVALID}),
            )

        if self._samples and sample.timestamp_s <= self._samples[-1].timestamp_s:
            return SignalAnalysis(
                sample=sample,
                metrics=SignalMetrics(
                    d_voltage_v_per_min=None,
                    d_current_a_per_min=None,
                    d_temp_c_per_min=None,
                    current_min_a=self._current_min_a,
                    seconds_since_current_min=None,
                    delta_current_from_min_a=None,
                    current_plateau_span_a=None,
                    current_plateau_center_a=None,
                    reversal_confirmations=self._reversal_confirmations,
                ),
                events=frozenset({SignalEvent.TELEMETRY_INVALID}),
            )

        self._samples.append(sample)
        events: set[SignalEvent] = set()
        self._update_minimum(sample, events)

        rate_window = self._window(sample.timestamp_s, self.config.rate_window_s)
        du = self._rate_per_min(rate_window, "voltage_v")
        di = self._rate_per_min(rate_window, "current_a")
        dt = self._rate_per_min(rate_window, "temp_c")

        plateau_span, plateau_center, is_plateau = self._plateau_metrics(sample.timestamp_s)
        if is_plateau:
            events.add(SignalEvent.CURRENT_PLATEAU)

        self._update_reversal(sample, events)

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

        thermal_acceleration = (
            dt is not None
            and di is not None
            and dt >= self.config.thermal_warn_c_per_min
            and di >= self.config.min_current_rise_for_thermal_a_per_min
        )
        if thermal_acceleration:
            events.add(SignalEvent.THERMAL_ACCELERATION)

        reversal_now = (
            SignalEvent.CURRENT_REVERSAL_CONFIRMED in events or self._reversal_emitted
        )
        voltage_sag = (
            reversal_now
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
        if reversal_now and near_target and not thermal_acceleration and not voltage_sag:
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
                current_plateau_span_a=plateau_span,
                current_plateau_center_a=plateau_center,
                reversal_confirmations=self._reversal_confirmations,
            ),
            events=frozenset(events),
        )
