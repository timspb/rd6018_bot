"""Module-owned Pb automatic voltage ceilings and warning values."""

from __future__ import annotations

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec


PB_AUTOMATIC_TARGET_CEILING_V = VariableSpec(
    key="safety.voltage.pb_automatic_target_ceiling_v",
    default=16.6,
    value_type=float,
    unit="V",
    description="Hard software ceiling applied to automatic Pb profile targets after temperature compensation.",
    owner="runtime.safety.voltage",
    provenance="accepted production legacy Pb profile ceiling formerly config.MAX_VOLTAGE",
    override_policy=OverridePolicy.DEPLOYMENT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=12.0,
    maximum=18.0,
)

PB_PROFILE_WARNING_VOLTAGE_V = VariableSpec(
    key="safety.voltage.pb_profile_warning_v",
    default=float(PB_AUTOMATIC_TARGET_CEILING_V.default),
    value_type=float,
    unit="V",
    description="Pb automatic-profile voltage above which the runtime emits an operator warning outside Manual mode.",
    owner="runtime.safety.voltage",
    provenance="same accepted Pb profile ceiling; warning fires when measured voltage exceeds the automatic target ceiling",
    override_policy=OverridePolicy.DEPLOYMENT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=12.0,
    maximum=18.0,
)


def clamp_pb_automatic_target_voltage(voltage_v: float) -> float:
    return round(
        min(
            float(PB_AUTOMATIC_TARGET_CEILING_V.default),
            max(0.0, float(voltage_v)),
        ),
        2,
    )


__all__ = [
    "PB_AUTOMATIC_TARGET_CEILING_V",
    "PB_PROFILE_WARNING_VOLTAGE_V",
    "clamp_pb_automatic_target_voltage",
]
