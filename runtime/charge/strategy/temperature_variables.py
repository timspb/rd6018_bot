"""Module-owned automatic charge temperature-compensation values."""

from __future__ import annotations

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec


TEMPERATURE_REFERENCE_C = VariableSpec(
    key="charge.temperature.reference_c",
    default=25.0,
    value_type=float,
    unit="C",
    description="Reference battery temperature for automatic Pb voltage compensation.",
    owner="runtime.charge.strategy.temperature",
    provenance="accepted production temperature compensation reference",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=-20.0,
    maximum=60.0,
)

TEMPERATURE_MAX_DELTA_V = VariableSpec(
    key="charge.temperature.max_delta_v",
    default=0.60,
    value_type=float,
    unit="V",
    description="Absolute bound for automatic temperature voltage correction.",
    owner="runtime.charge.strategy.temperature",
    provenance="accepted production compensation bound",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=2.0,
)

CA_EFB_COMPENSATION_V_PER_C = VariableSpec(
    key="charge.temperature.ca_efb_v_per_c",
    default=0.018,
    value_type=float,
    unit="V/C",
    description="Ca/Ca and EFB automatic voltage compensation coefficient.",
    owner="runtime.charge.strategy.temperature",
    provenance="accepted production Ca/EFB coefficient",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=0.05,
)

AGM_COMPENSATION_V_PER_C = VariableSpec(
    key="charge.temperature.agm_v_per_c",
    default=0.016,
    value_type=float,
    unit="V/C",
    description="AGM automatic voltage compensation coefficient.",
    owner="runtime.charge.strategy.temperature",
    provenance="accepted production AGM coefficient",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=0.05,
)

CUSTOM_COMPENSATION_V_PER_C = VariableSpec(
    key="charge.temperature.custom_v_per_c",
    default=0.018,
    value_type=float,
    unit="V/C",
    description="Characterization-only Custom compensation coefficient.",
    owner="runtime.charge.strategy.temperature",
    provenance="accepted historical Custom coefficient",
    override_policy=OverridePolicy.CODE_DEFAULT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=0.0,
    maximum=0.05,
)


__all__ = [
    "AGM_COMPENSATION_V_PER_C",
    "CA_EFB_COMPENSATION_V_PER_C",
    "CUSTOM_COMPENSATION_V_PER_C",
    "TEMPERATURE_MAX_DELTA_V",
    "TEMPERATURE_REFERENCE_C",
]
