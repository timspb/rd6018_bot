"""Canonical reference Delta values used by charge UI/compatibility surfaces."""

from __future__ import annotations

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec


MIX_CC_DELTA_V_EXIT_V = VariableSpec(
    key="charge.mix.cc_delta_v_exit_v",
    default=0.03,
    value_type=float,
    unit="V",
    description="Reference CC MIX voltage-drop Delta used by compatibility/operator surfaces.",
    owner="runtime.charge.strategy.mix",
    provenance="accepted production Delta-V reference",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.001,
    maximum=1.0,
)

MIX_CV_DELTA_I_RATIO = VariableSpec(
    key="charge.mix.cv_delta_i_ratio",
    default=0.30,
    value_type=float,
    unit="ratio",
    description="CV MIX current-rise threshold as a fraction of the observed current minimum.",
    owner="runtime.charge.strategy.mix",
    provenance="accepted production 30 percent current-reversal rule",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=2.0,
)

MIX_CV_DELTA_I_EXIT_A = VariableSpec(
    key="charge.mix.cv_delta_i_exit_a",
    default=0.03,
    value_type=float,
    unit="A",
    description="Reference CV MIX current-rise Delta used by compatibility/operator surfaces.",
    owner="runtime.charge.strategy.mix",
    provenance="accepted production Delta-I floor/reference",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.001,
    maximum=5.0,
)


__all__ = [
    "MIX_CC_DELTA_V_EXIT_V",
    "MIX_CV_DELTA_I_EXIT_A",
    "MIX_CV_DELTA_I_RATIO",
]
