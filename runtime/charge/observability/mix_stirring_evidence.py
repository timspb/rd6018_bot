"""Passive EFB MIX stirring-current evidence; never a charge-control policy.

All thresholds are *candidate calibration values*. This module does not select
voltages, mutate charge state, or produce executable charging intents.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

DIAGNOSTIC_CODE = "MIX_STIR_CURRENT_INSUFFICIENT"


@dataclass(frozen=True)
class StirringCandidateConfig:
    # Draft evidence thresholds, NOT an EFB voltage-raising authorization.
    fast_ceiling_s: float = 25 * 60
    low_current_c: float = 0.02
    nominal_program_c: float = 0.03
    program_c_tolerance: float = 0.005
    ceiling_tolerance_v: float = 0.05
    confirmation_s: float = 180.0
    confirmation_windows: int = 3
    max_sample_gap_s: float = 90.0

    def __post_init__(self) -> None:
        values = (
            self.fast_ceiling_s, self.low_current_c, self.nominal_program_c,
            self.program_c_tolerance, self.ceiling_tolerance_v,
            self.confirmation_s, self.max_sample_gap_s,
        )
        if not all(math.isfinite(v) and v > 0 for v in values):
            raise ValueError("candidate settings must be finite and positive")
        if self.confirmation_windows < 2:
            raise ValueError("multiple independent windows are required")


@dataclass(frozen=True)
class MixEvidencePoint:
    timestamp_s: float
    battery_voltage_v: float
    battery_current_a: float
    voltage_setpoint_readback_v: float
    current_setpoint_readback_a: float
    battery_temperature_c: float | None
    # Explicit evidence from the actual output register, not inferred from I>0.
    output_on: bool | None
    is_cv: bool | None
    sources_fresh: bool
    # Existing SignalAnalyzer event, computed on a VALID sample.
    thermal_acceleration: bool | None
    safety_clear: bool | None


@dataclass(frozen=True)
class StirringAssessment:
    status: str
    reason: str
    diagnostic_code: str | None = None
    first_ceiling_elapsed_s: float | None = None
    confirmed_low_current_c: float | None = None
    temperature_rate_c_per_min: float | None = None

    @property
    def actuator_authority(self) -> bool:
        return False


def _valid(p: MixEvidencePoint) -> bool:
    numbers = (
        p.timestamp_s, p.battery_voltage_v, p.battery_current_a,
        p.voltage_setpoint_readback_v, p.current_setpoint_readback_a,
    )
    return (
        all(isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v) for v in numbers)
        and p.timestamp_s >= 0 and p.battery_voltage_v > 0
        and p.battery_current_a >= 0 and p.current_setpoint_readback_a > 0
        and p.voltage_setpoint_readback_v > 0
        and (p.battery_temperature_c is None
             or (math.isfinite(p.battery_temperature_c)
                 and -50 <= p.battery_temperature_c <= 100))
    )


def assess_mix_stirring(
    points: Sequence[MixEvidencePoint],
    *,
    profile: str,
    capacity_ah: float,
    mix_started_at_s: float,
    configured_ceiling_v: float,
    delta_confirmed: bool | None,
    config: StirringCandidateConfig | None = None,
) -> StirringAssessment:
    """Classify an observational candidate; never recommend or authorize >Umax.

    Input must be from one explicitly identified session/MIX epoch. Missing
    history is not silently synthesized, and post-Delta hold is untouched.
    """
    cfg = config or StirringCandidateConfig()
    def pending(reason: str) -> StirringAssessment:
        return StirringAssessment("insufficient_evidence", reason)

    chemistry = str(profile).strip().upper()
    if chemistry not in {"EFB", "CA/CA"}:
        return StirringAssessment("excluded", "profile_not_in_scope")
    if chemistry != "EFB":
        return StirringAssessment("observational_only", "ca_ca_not_escalation_candidate")
    if delta_confirmed is not False:
        return pending("delta_confirmed_or_unknown")
    if not (math.isfinite(capacity_ah) and capacity_ah > 0
            and math.isfinite(mix_started_at_s) and mix_started_at_s >= 0
            and math.isfinite(configured_ceiling_v) and configured_ceiling_v > 0):
        return pending("invalid_session_parameters")
    if not points:
        return pending("no_samples")
    if any(not _valid(p) for p in points):
        return pending("invalid_sample")
    if (points[0].timestamp_s < mix_started_at_s
            or any(b.timestamp_s <= a.timestamp_s
                   for a, b in zip(points, points[1:]))):
        return pending("out_of_order_or_wrong_epoch")

    def at_ceiling(p: MixEvidencePoint) -> bool:
        return (
            p.is_cv is True
            and abs(p.voltage_setpoint_readback_v - configured_ceiling_v)
                <= cfg.ceiling_tolerance_v
            and abs(p.battery_voltage_v - configured_ceiling_v)
                <= cfg.ceiling_tolerance_v
        )

    # A setpoint alone is not proof that the charger actually reached Umax.
    first_ceiling = next((
        p.timestamp_s - mix_started_at_s for p in points
        if p.sources_fresh and p.output_on is True and at_ceiling(p)
    ), None)
    if first_ceiling is None:
        return pending("ceiling_not_physically_observed")
    if first_ceiling > cfg.fast_ceiling_s:
        return StirringAssessment(
            "not_candidate", "ceiling_reached_too_late",
            first_ceiling_elapsed_s=first_ceiling,
        )
    end = points[-1].timestamp_s
    begin = end - cfg.confirmation_s
    eligible = [p for p in points if p.timestamp_s >= begin]
    if not eligible or eligible[0].timestamp_s > begin + cfg.max_sample_gap_s:
        return pending("confirmation_window_incomplete")
    if any(b.timestamp_s - a.timestamp_s > cfg.max_sample_gap_s
           for a, b in zip(eligible, eligible[1:])):
        return pending("confirmation_gap")
    width = cfg.confirmation_s / cfg.confirmation_windows
    for i in range(cfg.confirmation_windows):
        low, high = begin + i * width, begin + (i + 1) * width
        bucket = [p for p in eligible if
                  low <= p.timestamp_s < high or
                  (i == cfg.confirmation_windows - 1 and p.timestamp_s == high)]
        if not bucket:
            return pending("missing_independent_confirmation_window")

    # Unknown source/output/safety/thermal status is NOT an explicit negative.
    if any(p.sources_fresh is not True or p.output_on is not True
           for p in eligible):
        return pending("unverified_active_output_or_stale_evidence")
    if any(p.safety_clear is not True for p in eligible):
        return pending("safety_evidence_unknown_or_fault")
    if any(p.thermal_acceleration is not False for p in eligible):
        return pending("thermal_acceleration_or_unassessed")
    if not all(at_ceiling(p) for p in eligible):
        return pending("not_continuously_at_voltage_ceiling")
    if any(abs(p.current_setpoint_readback_a / capacity_ah
               - cfg.nominal_program_c) > cfg.program_c_tolerance
           for p in eligible):
        return pending("current_program_not_nominal_mix")
    if any(p.battery_current_a / capacity_ah >= cfg.low_current_c
           for p in eligible):
        return StirringAssessment(
            "not_candidate", "measured_current_not_persistently_low",
            first_ceiling_elapsed_s=first_ceiling,
        )
    first_temp, last_temp = eligible[0].battery_temperature_c, eligible[-1].battery_temperature_c
    rate = None
    if first_temp is not None and last_temp is not None:
        duration = eligible[-1].timestamp_s - eligible[0].timestamp_s
        if duration > 0:
            rate = (last_temp - first_temp) * 60 / duration

    return StirringAssessment(
        status="candidate", reason="early_ceiling_with_sustained_low_c_rate",
        diagnostic_code=DIAGNOSTIC_CODE,
        first_ceiling_elapsed_s=first_ceiling,
        confirmed_low_current_c=max(p.battery_current_a for p in eligible) / capacity_ah,
        temperature_rate_c_per_min=rate,
    )


__all__ = [
    "DIAGNOSTIC_CODE", "MixEvidencePoint", "StirringAssessment",
    "StirringCandidateConfig", "assess_mix_stirring",
]
