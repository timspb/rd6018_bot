"""Module-owned variables for bounded intermediate DESULFATION."""

from __future__ import annotations

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec


DESULFATION_DURATION_HOURS = VariableSpec(
    key="charge.desulfation.duration_hours",
    default=2.0,
    value_type=float,
    unit="h",
    description="Active DESULFATION duration before the recovery SAFE_WAIT transition.",
    owner="runtime.charge.strategy.desulfation",
    provenance="accepted production bounded intermediate recovery duration",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=24.0,
)

DESULFATION_BASE_VOLTAGE_V = VariableSpec(
    key="charge.desulfation.base_voltage_v",
    default=16.3,
    value_type=float,
    unit="V",
    description="DESULFATION base voltage before temperature compensation and recipe bounding.",
    owner="runtime.charge.strategy.desulfation",
    provenance="accepted production intermediate recovery target",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=12.0,
    maximum=17.5,
)

DESULFATION_CURRENT_C_RATE = VariableSpec(
    key="charge.desulfation.current_c_rate",
    default=0.02,
    value_type=float,
    unit="C",
    description="DESULFATION target current as a fraction of nominal battery capacity.",
    owner="runtime.charge.strategy.desulfation",
    provenance="accepted production intermediate recovery 0.02C rule",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=0.10,
)

DESULFATION_MIN_CURRENT_A = VariableSpec(
    key="charge.desulfation.minimum_target_current_a",
    default=0.1,
    value_type=float,
    unit="A",
    description="Minimum non-zero DESULFATION target current for very small declared capacities.",
    owner="runtime.charge.strategy.desulfation",
    provenance="accepted historical percent-of-capacity target floor",
    override_policy=OverridePolicy.CODE_DEFAULT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=0.0,
    maximum=1.0,
)

DESULFATION_OCP_MARGIN_A = VariableSpec(
    key="charge.desulfation.ocp_margin_a",
    default=1.0,
    value_type=float,
    unit="A",
    description="Additional DESULFATION OCP headroom used during the accepted startup transient.",
    owner="runtime.charge.strategy.desulfation",
    provenance="accepted production DESULFATION protection margin",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=5.0,
)


def desulfation_duration_seconds() -> float:
    return float(DESULFATION_DURATION_HOURS.default) * 3600.0


__all__ = [
    "DESULFATION_BASE_VOLTAGE_V",
    "DESULFATION_CURRENT_C_RATE",
    "DESULFATION_DURATION_HOURS",
    "DESULFATION_MIN_CURRENT_A",
    "DESULFATION_OCP_MARGIN_A",
    "desulfation_duration_seconds",
]
