"""Module-owned values for the automatic PREP / soft-start stage."""

from __future__ import annotations

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec


PREP_VOLTAGE_V = VariableSpec(
    key="charge.prep.voltage_v",
    default=12.0,
    value_type=float,
    unit="V",
    description="Soft-start voltage target and transition threshold into MAIN.",
    owner="runtime.charge.strategy.prep",
    provenance="accepted production PREP 12 V threshold",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=10.0,
    maximum=14.0,
)

PREP_CURRENT_C_RATE = VariableSpec(
    key="charge.prep.current_c_rate",
    default=0.01,
    value_type=float,
    unit="C",
    description="PREP current target as a fraction of declared battery capacity.",
    owner="runtime.charge.strategy.prep",
    provenance="accepted production soft-start 0.01C current",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.001,
    maximum=0.05,
)

PREP_MIN_CURRENT_A = VariableSpec(
    key="charge.prep.minimum_current_a",
    default=0.1,
    value_type=float,
    unit="A",
    description="Minimum PREP current target for very small declared capacities.",
    owner="runtime.charge.strategy.prep",
    provenance="accepted historical percent-of-capacity current floor",
    override_policy=OverridePolicy.CODE_DEFAULT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=0.0,
    maximum=1.0,
)


__all__ = [
    "PREP_CURRENT_C_RATE",
    "PREP_MIN_CURRENT_A",
    "PREP_VOLTAGE_V",
]
