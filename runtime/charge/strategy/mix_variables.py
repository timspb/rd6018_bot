"""Module-owned variables for authoritative automatic MIX strategy."""

from __future__ import annotations

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec


CA_MIX_VOLTAGE_V = VariableSpec(
    key="charge.mix.ca_voltage_v",
    default=16.5,
    value_type=float,
    unit="V",
    description="Ca/Ca automatic MIX base voltage before temperature compensation.",
    owner="runtime.charge.strategy.mix",
    provenance="accepted production Ca/Ca MIX program",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=12.0,
    maximum=17.5,
)

EFB_MIX_VOLTAGE_V = VariableSpec(
    key="charge.mix.efb_voltage_v",
    default=16.5,
    value_type=float,
    unit="V",
    description="EFB automatic MIX base voltage before temperature compensation.",
    owner="runtime.charge.strategy.mix",
    provenance="accepted production generic EFB MIX ceiling",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=12.0,
    maximum=17.5,
)

AGM_MIX_VOLTAGE_V = VariableSpec(
    key="charge.mix.agm_voltage_v",
    default=16.3,
    value_type=float,
    unit="V",
    description="AGM automatic MIX base voltage before temperature compensation.",
    owner="runtime.charge.strategy.mix",
    provenance="accepted production AGM MIX program",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=12.0,
    maximum=17.5,
)

MIX_CURRENT_C_RATE = VariableSpec(
    key="charge.mix.current_c_rate",
    default=0.03,
    value_type=float,
    unit="C",
    description="Automatic MIX target current as a fraction of nominal capacity.",
    owner="runtime.charge.strategy.mix",
    provenance="accepted production MIX 0.03C rule",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=0.10,
)

MIX_MIN_CURRENT_A = VariableSpec(
    key="charge.mix.minimum_target_current_a",
    default=0.1,
    value_type=float,
    unit="A",
    description="Minimum non-zero automatic MIX target current.",
    owner="runtime.charge.strategy.mix",
    provenance="accepted historical percent-of-capacity target floor",
    override_policy=OverridePolicy.CODE_DEFAULT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=0.0,
    maximum=1.0,
)

MIX_FINISH_HOLD_HOURS = VariableSpec(
    key="charge.mix.finish_hold_hours",
    default=2.0,
    value_type=float,
    unit="h",
    description="Sticky hold after accepted mode-specific MIX Delta evidence.",
    owner="runtime.charge.strategy.mix",
    provenance="accepted production sticky MIX finish hold",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=12.0,
)

CA_MIX_MAX_ACTIVE_HOURS = VariableSpec(
    key="charge.mix.ca_max_active_hours",
    default=20.0,
    value_type=float,
    unit="h",
    description="Maximum automatic active-MIX authority for Ca/Ca.",
    owner="runtime.charge.strategy.mix",
    provenance="accepted production active-MIX authority ceiling",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=72.0,
)

EFB_MIX_MAX_ACTIVE_HOURS = VariableSpec(
    key="charge.mix.efb_max_active_hours",
    default=24.0,
    value_type=float,
    unit="h",
    description="Maximum automatic active-MIX authority for EFB.",
    owner="runtime.charge.strategy.mix",
    provenance="accepted production active-MIX authority ceiling",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=72.0,
)

AGM_MIX_MAX_ACTIVE_HOURS = VariableSpec(
    key="charge.mix.agm_max_active_hours",
    default=10.0,
    value_type=float,
    unit="h",
    description="Maximum automatic active-MIX authority for AGM.",
    owner="runtime.charge.strategy.mix",
    provenance="accepted production active-MIX authority ceiling",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=72.0,
)


def mix_finish_hold_seconds() -> float:
    return float(MIX_FINISH_HOLD_HOURS.default) * 3600.0


def mix_max_active_seconds(profile: str) -> float:
    if str(profile) == "AGM":
        hours = AGM_MIX_MAX_ACTIVE_HOURS
    elif str(profile) == "EFB":
        hours = EFB_MIX_MAX_ACTIVE_HOURS
    else:
        hours = CA_MIX_MAX_ACTIVE_HOURS
    return float(hours.default) * 3600.0


__all__ = [
    "AGM_MIX_MAX_ACTIVE_HOURS",
    "AGM_MIX_VOLTAGE_V",
    "CA_MIX_MAX_ACTIVE_HOURS",
    "CA_MIX_VOLTAGE_V",
    "EFB_MIX_MAX_ACTIVE_HOURS",
    "EFB_MIX_VOLTAGE_V",
    "MIX_CURRENT_C_RATE",
    "MIX_FINISH_HOLD_HOURS",
    "MIX_MIN_CURRENT_A",
    "mix_finish_hold_seconds",
    "mix_max_active_seconds",
]
