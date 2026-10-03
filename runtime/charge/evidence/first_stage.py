"""Canonical pure first-stage evidence for MAIN.

The module accepts chemistry-like values at the boundary and normalizes only the
stable value/name; it has no dependency on production/legacy domain modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

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
    "assess_first_stage",
    "tail_c_rate",
    "tail_current_threshold_a",
]
