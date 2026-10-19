"""Canonical pure first-stage evidence for MAIN.

The module accepts chemistry-like values at the boundary and normalizes only the
stable value/name; it has no dependency on production/legacy domain modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, FrozenSet, Optional

from .first_stage_variables import (
    AGM_TAIL_C_RATE,
    CURRENT_NOT_FALLING_A_PER_MIN,
    MAX_TAIL_A,
    MIN_MEASURABLE_TAIL_A,
    NEAR_TARGET_MARGIN_V,
    STANDARD_TAIL_C_RATE,
    THERMAL_ACCEL_C_PER_MIN,
    THERMAL_ANOMALY_MIN_TEMP_C,
    VOLTAGE_SAG_V_PER_MIN,
)


class FirstStageState(str, Enum):
    BULK_OR_TAPER = "bulk_or_taper"
    TAIL_READY = "tail_ready"
    STUCK_PLATEAU = "stuck_plateau"
    THERMALLY_UNSTABLE = "thermally_unstable"
    VOLTAGE_UNSTABLE = "voltage_unstable"
    TELEMETRY_INVALID = "telemetry_invalid"


@dataclass(frozen=True)
class FirstStageAssessment:
    state: FirstStageState
    current_c_rate: Optional[float]
    tail_threshold_a: float
    tail_threshold_c: float
    near_target: bool
    reason: str


@dataclass(frozen=True)
class MainSampleEvidenceInput:
    """One already-analyzed MAIN observation, with no actuator authority."""

    stage: str
    main_stage: str
    target_voltage_v: Optional[float]
    timestamp_s: float
    voltage_v: float
    current_a: float
    is_cv: bool
    chemistry: Any
    capacity_ah: float
    plateau_required_minutes: float
    plateau_window_minutes: float
    events: FrozenSet[Any]
    dtemp_c_per_min: Optional[float]
    dcurrent_a_per_min: Optional[float]
    dvoltage_v_per_min: Optional[float]
    temperature_c: Optional[float]


@dataclass(frozen=True)
class MainSampleEvidence:
    assessment: Optional[FirstStageAssessment]
    plateau_since_s: Optional[float]


class MainSampleEvidenceEvaluator:
    """Own the restart-local MAIN plateau clock and first-stage assessment."""

    def __init__(self) -> None:
        self.plateau_since_s: Optional[float] = None

    def reset(self) -> None:
        self.plateau_since_s = None

    def shift_clock(self, seconds: float) -> None:
        if self.plateau_since_s is not None and seconds > 0:
            self.plateau_since_s += float(seconds)

    def assess(self, sample: MainSampleEvidenceInput) -> MainSampleEvidence:
        if sample.stage != sample.main_stage or sample.target_voltage_v is None:
            self.reset()
            return MainSampleEvidence(None, None)
        target = float(sample.target_voltage_v)
        if not math.isfinite(target):
            self.reset()
            return MainSampleEvidence(None, None)
        qualifies = False
        try:
            threshold = tail_current_threshold_a(sample.chemistry, sample.capacity_ah)
            near_target = float(sample.voltage_v) >= target - float(NEAR_TARGET_MARGIN_V.default)
            current = float(sample.current_a)
        except (TypeError, ValueError):
            self.reset()
        else:
            if not sample.is_cv or any(
                getattr(event, "value", event) == "current_minimum_updated"
                for event in sample.events
            ):
                self.reset()
                qualifies = False
            else:
                qualifies = near_target and current > threshold and any(
                    getattr(event, "value", event) == "current_plateau" for event in sample.events
                )
        if not qualifies:
            self.reset()
            plateau_since = None
        else:
            if self.plateau_since_s is None:
                # Preserve accepted parity: CURRENT_PLATEAU already represents a
                # 15-minute window, so its first timestamp is backdated by that window.
                self.plateau_since_s = max(
                    0.0,
                    float(sample.timestamp_s) - float(sample.plateau_window_minutes) * 60.0,
                )
            plateau_since = self.plateau_since_s

        plateau_minutes = (
            max(0.0, (float(sample.timestamp_s) - float(plateau_since)) / 60.0)
            if plateau_since is not None else 0.0
        )
        assessment = assess_first_stage(
            chemistry=sample.chemistry,
            capacity_ah=float(sample.capacity_ah),
            voltage_v=_finite_or_nan(sample.voltage_v),
            current_a=_finite_or_nan(sample.current_a),
            target_voltage_v=target,
            is_cv=bool(sample.is_cv),
            plateau_minutes=plateau_minutes,
            required_plateau_minutes=float(sample.plateau_required_minutes),
            dtemp_c_per_min=sample.dtemp_c_per_min,
            dcurrent_a_per_min=sample.dcurrent_a_per_min,
            dvoltage_v_per_min=sample.dvoltage_v_per_min,
            temperature_c=sample.temperature_c,
        )
        return MainSampleEvidence(assessment, self.plateau_since_s)


def _finite_or_nan(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def _chemistry_key(chemistry: Any) -> str:
    raw = getattr(chemistry, "value", chemistry)
    key = str(raw).strip().lower().replace("/", "_").replace("-", "_")
    aliases = {
        "ca": "ca_ca",
        "calcium": "ca_ca",
    }
    return aliases.get(key, key)


def tail_c_rate(chemistry: Any) -> float:
    key = _chemistry_key(chemistry)
    if key == "agm":
        return float(AGM_TAIL_C_RATE.default)
    if key in {"efb", "ca_ca", "flooded", "custom"}:
        return float(STANDARD_TAIL_C_RATE.default)
    raise ValueError(f"unsupported battery chemistry for first-stage evidence: {chemistry!r}")


def tail_current_threshold_a(
    chemistry: Any,
    capacity_ah: float,
) -> float:
    capacity = float(capacity_ah)
    if capacity <= 0:
        raise ValueError("capacity_ah must be positive")
    c_rate = tail_c_rate(chemistry)
    return min(
        float(MAX_TAIL_A.default),
        max(float(MIN_MEASURABLE_TAIL_A.default), capacity * c_rate),
    )


def assess_first_stage(
    *,
    chemistry: Any,
    capacity_ah: float,
    voltage_v: float,
    current_a: float,
    target_voltage_v: float,
    is_cv: bool,
    plateau_minutes: float = 0.0,
    required_plateau_minutes: float = 40.0,
    dtemp_c_per_min: Optional[float] = None,
    dcurrent_a_per_min: Optional[float] = None,
    dvoltage_v_per_min: Optional[float] = None,
    temperature_c: Optional[float] = None,
) -> FirstStageAssessment:
    capacity = float(capacity_ah)
    voltage = float(voltage_v)
    current = float(current_a)
    target = float(target_voltage_v)
    threshold_a = tail_current_threshold_a(chemistry, capacity)
    threshold_c = tail_c_rate(chemistry)

    if not (0.0 < voltage < 25.0) or not (0.0 <= current <= 30.0) or not (0.0 < target < 25.0):
        return FirstStageAssessment(
            FirstStageState.TELEMETRY_INVALID,
            None,
            threshold_a,
            threshold_c,
            False,
            "invalid U/I/target telemetry",
        )

    current_c = current / capacity
    near_target = voltage >= target - float(NEAR_TARGET_MARGIN_V.default)
    current_not_falling = (
        dcurrent_a_per_min is not None
        and float(dcurrent_a_per_min) >= float(CURRENT_NOT_FALLING_A_PER_MIN.default)
    )

    if (
        is_cv
        and temperature_c is not None
        and float(temperature_c) >= float(THERMAL_ANOMALY_MIN_TEMP_C.default)
        and near_target
        and current_not_falling
        and dtemp_c_per_min is not None
        and float(dtemp_c_per_min) >= float(THERMAL_ACCEL_C_PER_MIN.default)
    ):
        return FirstStageAssessment(
            FirstStageState.THERMALLY_UNSTABLE,
            current_c,
            threshold_a,
            threshold_c,
            near_target,
            (
                f"CV dI/dt={float(dcurrent_a_per_min):+.3f}A/min with "
                f"dT/dt={float(dtemp_c_per_min):.3f}C/min"
            ),
        )

    if (
        is_cv
        and near_target
        and dvoltage_v_per_min is not None
        and float(dvoltage_v_per_min) <= float(VOLTAGE_SAG_V_PER_MIN.default)
    ):
        return FirstStageAssessment(
            FirstStageState.VOLTAGE_UNSTABLE,
            current_c,
            threshold_a,
            threshold_c,
            near_target,
            f"CV dU/dt={float(dvoltage_v_per_min):.3f}V/min near target",
        )

    if is_cv and near_target and current <= threshold_a:
        return FirstStageAssessment(
            FirstStageState.TAIL_READY,
            current_c,
            threshold_a,
            threshold_c,
            near_target,
            f"CV tail {current:.3f}A <= {threshold_a:.3f}A ({threshold_c:.4f}C)",
        )

    if (
        is_cv
        and near_target
        and current > threshold_a
        and float(plateau_minutes) >= float(required_plateau_minutes)
    ):
        return FirstStageAssessment(
            FirstStageState.STUCK_PLATEAU,
            current_c,
            threshold_a,
            threshold_c,
            near_target,
            f"CV plateau {float(plateau_minutes):.0f}min above {threshold_a:.3f}A",
        )

    return FirstStageAssessment(
        FirstStageState.BULK_OR_TAPER,
        current_c,
        threshold_a,
        threshold_c,
        near_target,
        "first-stage taper is still evolving",
    )


__all__ = [
    "FirstStageAssessment",
    "FirstStageState",
    "MainSampleEvidence",
    "MainSampleEvidenceEvaluator",
    "MainSampleEvidenceInput",
    "assess_first_stage",
    "tail_c_rate",
    "tail_current_threshold_a",
]
