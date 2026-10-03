"""Module-owned external-battery thermal safety thresholds."""

from __future__ import annotations

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec


BATTERY_TEMP_WARNING_C = VariableSpec(
    key="safety.thermal.battery_warning_c",
    default=35.0,
    value_type=float,
    unit="degC",
    description="External battery temperature that emits one warning per session.",
    owner="runtime.safety.thermal",
    provenance="accepted production battery thermal warning threshold",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=-20.0,
    maximum=80.0,
)

BATTERY_TEMP_PAUSE_C = VariableSpec(
    key="safety.thermal.battery_pause_c",
    default=40.0,
    value_type=float,
    unit="degC",
    description="External battery temperature that pauses automatic charging and enters cooling.",
    owner="runtime.safety.thermal",
    provenance="accepted production thermal pause threshold",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=-20.0,
    maximum=80.0,
)

BATTERY_TEMP_CRITICAL_C = VariableSpec(
    key="safety.thermal.battery_critical_c",
    default=45.0,
    value_type=float,
    unit="degC",
    description="External battery temperature that triggers fail-closed emergency reset.",
    owner="runtime.safety.thermal",
    provenance="accepted production critical battery temperature",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=-20.0,
    maximum=100.0,
)


__all__ = [
    "BATTERY_TEMP_CRITICAL_C",
    "BATTERY_TEMP_PAUSE_C",
    "BATTERY_TEMP_WARNING_C",
]
