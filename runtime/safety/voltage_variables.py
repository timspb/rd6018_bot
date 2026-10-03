"""Module-owned voltage warning values.

This is a warning boundary, not the physical execution envelope.
"""

from __future__ import annotations

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec


PB_PROFILE_WARNING_VOLTAGE_V = VariableSpec(
    key="safety.voltage.pb_profile_warning_v",
    default=16.6,
    value_type=float,
    unit="V",
    description="Pb automatic-profile voltage above which the runtime emits an operator warning outside Manual mode.",
    owner="runtime.safety.voltage",
    provenance="accepted legacy Pb profile warning ceiling; physical ceilings are enforced separately",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=12.0,
    maximum=18.0,
)


__all__ = ["PB_PROFILE_WARNING_VOLTAGE_V"]
