"""Module-owned variables for the charge-domain SAFE_WAIT relaxation stage."""

from __future__ import annotations

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec


SAFE_WAIT_TARGET_MARGIN_V = VariableSpec(
    key="charge.safe_wait.target_margin_v",
    default=0.5,
    value_type=float,
    unit="V",
    description="Voltage relaxation margin below the next-stage target that permits an early SAFE_WAIT exit.",
    owner="runtime.charge.strategy.safe_wait",
    provenance="accepted production HV-to-LV relaxation rule",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=3.0,
)

SAFE_WAIT_MAX_HOURS = VariableSpec(
    key="charge.safe_wait.maximum_hours",
    default=2.0,
    value_type=float,
    unit="h",
    description="Maximum SAFE_WAIT relaxation time before continuation may be attempted.",
    owner="runtime.charge.strategy.safe_wait",
    provenance="accepted production anti-stall SAFE_WAIT maximum",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=24.0,
)


def safe_wait_max_seconds() -> float:
    return float(SAFE_WAIT_MAX_HOURS.default) * 3600.0


__all__ = [
    "SAFE_WAIT_MAX_HOURS",
    "SAFE_WAIT_TARGET_MARGIN_V",
    "safe_wait_max_seconds",
]
