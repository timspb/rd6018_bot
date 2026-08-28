from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pb_domain import BatteryChemistry


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


# The historical 0.2/0.3 A boundaries happen to be in the neighborhood of a
# few-thousandths C for a 60–80 Ah automotive battery. Expressing the boundary
# as C-rate preserves that intent across battery sizes instead of treating a
# 45 Ah and 200 Ah battery identically.
TAIL_C_RATE = {
    BatteryChemistry.AGM: 0.0030,
    BatteryChemistry.EFB: 0.0040,
    BatteryChemistry.CA_CA: 0.0040,
    BatteryChemistry.FLOODED: 0.0040,
    BatteryChemistry.CUSTOM: 0.0040,
}

MIN_MEASURABLE_TAIL_A = 0.05
MAX_TAIL_A = 1.50
NEAR_TARGET_MARGIN_V = 0.20
THERMAL_ACCEL_C_PER_MIN = 0.12
CURRENT_NOT_FALLING_A_PER_MIN = -0.01
VOLTAGE_SAG_V_PER_MIN = -0.01


def tail_current_threshold_a(
    chemistry: BatteryChemistry,
    capacity_ah: float,
) -> float:
    capacity = float(capacity_ah)
    if capacity <= 0:
        raise ValueError("capacity_ah must be positive")
    c_rate = TAIL_C_RATE[chemistry]
    return min(MAX_TAIL_A, max(MIN_MEASURABLE_TAIL_A, capacity * c_rate))


def assess_first_stage(
    *,
    chemistry: BatteryChemistry,
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
) -> FirstStageAssessment:
    capacity = float(capacity_ah)
    voltage = float(voltage_v)
    current = float(current_a)
    target = float(target_voltage_v)
    threshold_a = tail_current_threshold_a(chemistry, capacity)
    threshold_c = TAIL_C_RATE[chemistry]

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
    near_target = voltage >= target - NEAR_TARGET_MARGIN_V
    current_not_falling = (
        dcurrent_a_per_min is not None
        and float(dcurrent_a_per_min) >= CURRENT_NOT_FALLING_A_PER_MIN
    )

    # Heating during bulk/taper is not sufficient evidence of instability. The
    # practitioner warning pattern is compound: CV near target + current no longer
    # falling (or reversing) + temperature acceleration.
    if (
        is_cv
        and near_target
        and current_not_falling
        and dtemp_c_per_min is not None
        and float(dtemp_c_per_min) >= THERMAL_ACCEL_C_PER_MIN
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

    # Likewise, voltage sag matters here when it occurs in the CV/near-target tail,
    # not as a generic derivative during the normal rise toward absorption voltage.
    if (
        is_cv
        and near_target
        and dvoltage_v_per_min is not None
        and float(dvoltage_v_per_min) <= VOLTAGE_SAG_V_PER_MIN
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
