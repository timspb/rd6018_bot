"""Module-owned variables for MAIN first-stage evidence."""

from __future__ import annotations

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec


AGM_TAIL_C_RATE = VariableSpec(
    key="charge.evidence.first_stage.agm_tail_c_rate",
    default=0.0030,
    value_type=float,
    unit="C",
    description="AGM current C-rate at or below which near-target CV qualifies as tail-ready.",
    owner="runtime.charge.evidence.first_stage",
    provenance="accepted capacity-normalized AGM tail evidence",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=0.1,
)

STANDARD_TAIL_C_RATE = VariableSpec(
    key="charge.evidence.first_stage.standard_tail_c_rate",
    default=0.0040,
    value_type=float,
    unit="C",
    description="EFB/Ca-Ca/flooded current C-rate at or below which near-target CV qualifies as tail-ready.",
    owner="runtime.charge.evidence.first_stage",
    provenance="accepted capacity-normalized standard Pb tail evidence",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=0.1,
)

MIN_MEASURABLE_TAIL_A = VariableSpec(
    key="charge.evidence.first_stage.min_measurable_tail_a",
    default=0.05,
    value_type=float,
    unit="A",
    description="Lower clamp for capacity-normalized tail-current threshold.",
    owner="runtime.charge.evidence.first_stage",
    provenance="accepted telemetry/evidence floor",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=5.0,
)

MAX_TAIL_A = VariableSpec(
    key="charge.evidence.first_stage.max_tail_a",
    default=1.50,
    value_type=float,
    unit="A",
    description="Upper clamp for capacity-normalized tail-current threshold.",
    owner="runtime.charge.evidence.first_stage",
    provenance="accepted first-stage evidence ceiling",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=10.0,
)

NEAR_TARGET_MARGIN_V = VariableSpec(
    key="charge.evidence.first_stage.near_target_margin_v",
    default=0.20,
    value_type=float,
    unit="V",
    description="Voltage margin below MAIN target considered near-target for first-stage evidence.",
    owner="runtime.charge.evidence.first_stage",
    provenance="accepted first-stage near-target rule",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=2.0,
)

THERMAL_ACCEL_C_PER_MIN = VariableSpec(
    key="charge.evidence.first_stage.thermal_accel_c_per_min",
    default=0.12,
    value_type=float,
    unit="degC/min",
    description="External battery temperature rise rate contributing to unstable-CV evidence.",
    owner="runtime.charge.evidence.first_stage",
    provenance="accepted first-stage thermal anomaly rule",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=5.0,
)

THERMAL_ANOMALY_MIN_TEMP_C = VariableSpec(
    key="charge.evidence.first_stage.thermal_anomaly_min_temp_c",
    default=30.0,
    value_type=float,
    unit="degC",
    description="Minimum battery temperature at which thermal acceleration may classify first-stage CV as unstable.",
    owner="runtime.charge.evidence.first_stage",
    provenance="accepted first-stage thermal anomaly rule",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=-50.0,
    maximum=100.0,
)

CURRENT_NOT_FALLING_A_PER_MIN = VariableSpec(
    key="charge.evidence.first_stage.current_not_falling_a_per_min",
    default=-0.01,
    value_type=float,
    unit="A/min",
    description="Minimum current derivative treated as not materially falling during near-target CV.",
    owner="runtime.charge.evidence.first_stage",
    provenance="accepted first-stage current-trend rule",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=-10.0,
    maximum=10.0,
)

VOLTAGE_SAG_V_PER_MIN = VariableSpec(
    key="charge.evidence.first_stage.voltage_sag_v_per_min",
    default=-0.01,
    value_type=float,
    unit="V/min",
    description="Voltage derivative at or below which near-target CV is classified as voltage-unstable.",
    owner="runtime.charge.evidence.first_stage",
    provenance="accepted first-stage voltage-sag rule",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=-10.0,
    maximum=10.0,
)


__all__ = [
    "AGM_TAIL_C_RATE",
    "CURRENT_NOT_FALLING_A_PER_MIN",
    "MAX_TAIL_A",
    "MIN_MEASURABLE_TAIL_A",
    "NEAR_TARGET_MARGIN_V",
    "STANDARD_TAIL_C_RATE",
    "THERMAL_ACCEL_C_PER_MIN",
    "THERMAL_ANOMALY_MIN_TEMP_C",
    "VOLTAGE_SAG_V_PER_MIN",
]
