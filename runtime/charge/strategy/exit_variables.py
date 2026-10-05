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


__all__ = ["MIX_CC_DELTA_V_EXIT_V", "MIX_CV_DELTA_I_EXIT_A"]
