"""Module-owned variables for authoritative MAIN strategy.

Every value here has one semantic owner and self-describing metadata. Consumers
must import the declaration or derive from it; they must not copy literals.
"""

from __future__ import annotations

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec



CA_MAIN_VOLTAGE_V = VariableSpec(
    key="charge.main.ca_voltage_v",
    default=14.7,
    value_type=float,
    unit="V",
    description="Ca/Ca MAIN base voltage before temperature compensation.",
    owner="runtime.charge.strategy.main",
    provenance="accepted production Ca/Ca MAIN program",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=12.0,
    maximum=17.5,
)

EFB_MAIN_VOLTAGE_V = VariableSpec(
    key="charge.main.efb_voltage_v",
    default=14.8,
    value_type=float,
    unit="V",
    description="EFB MAIN base voltage before temperature compensation.",
    owner="runtime.charge.strategy.main",
    provenance="accepted production EFB MAIN program",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=12.0,
    maximum=17.5,
)

DEFAULT_MAIN_VOLTAGE_V = VariableSpec(
    key="charge.main.default_voltage_v",
    default=14.7,
    value_type=float,
    unit="V",
    description="Fallback Pb MAIN base voltage for profiles without a specific MAIN override.",
    owner="runtime.charge.strategy.main",
    provenance="accepted historical default MAIN voltage",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=12.0,
    maximum=17.5,
)

MAIN_CURRENT_C_RATE = VariableSpec(
    key="charge.main.current_c_rate",
    default=0.10,
    value_type=float,
    unit="C",
    description="MAIN target current as a fraction of nominal battery capacity.",
    owner="runtime.charge.strategy.main",
    provenance="accepted production MAIN 0.1C rule",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=0.30,
)

MAIN_FALLBACK_HOURS = VariableSpec(
    key="charge.main.fallback_hours",
    default=72.0,
    value_type=float,
    unit="h",
    description="Maximum MAIN elapsed time before the strategy fallback is evaluated.",
    owner="runtime.charge.strategy.main",
    provenance="accepted production MAIN strategy",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=1.0,
    maximum=168.0,
)

STANDARD_TAIL_HOLD_HOURS = VariableSpec(
    key="charge.main.standard_tail_hold_hours",
    default=3.0,
    value_type=float,
    unit="h",
    description="Continuous low-current tail hold for Ca/Ca, EFB and flooded MAIN.",
    owner="runtime.charge.strategy.main",
    provenance="accepted production MAIN strategy",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=24.0,
)

AGM_TAIL_HOLD_HOURS = VariableSpec(
    key="charge.main.agm_tail_hold_hours",
    default=2.0,
    value_type=float,
    unit="h",
    description="Continuous AGM low-current hold before step advance or MAIN exit.",
    owner="runtime.charge.strategy.main",
    provenance="accepted AGM stepped-charge strategy",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=24.0,
)

STANDARD_MAX_RECOVERY_ATTEMPTS = VariableSpec(
    key="charge.main.standard_max_recovery_attempts",
    default=3,
    value_type=int,
    unit="count",
    description="Session-wide bounded recovery attempts for Ca/Ca and EFB MAIN.",
    owner="runtime.charge.strategy.main",
    provenance="accepted production recovery budget",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0,
    maximum=20,
)

AGM_MAX_RECOVERY_ATTEMPTS = VariableSpec(
    key="charge.main.agm_max_recovery_attempts",
    default=4,
    value_type=int,
    unit="count",
    description="Session-wide bounded recovery attempts for AGM MAIN.",
    owner="runtime.charge.strategy.main",
    provenance="accepted AGM recovery budget",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0,
    maximum=20,
)

AGM_TIMEOUT_TAIL_CURRENT_A = VariableSpec(
    key="charge.main.agm_timeout_tail_current_a",
    default=0.20,
    value_type=float,
    unit="A",
    description="Maximum AGM current allowing MAIN timeout to continue to final Mix in CV.",
    owner="runtime.charge.strategy.main",
    provenance="accepted conservative AGM 72-hour fallback",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=5.0,
)

AGM_STAGE_VOLTAGES_V = VariableSpec(
    key="charge.main.agm_stage_voltages_v",
    default=(14.4, 14.6, 14.8, 15.0),
    value_type=tuple,
    unit="V",
    description="Ordered AGM MAIN voltage steps.",
    owner="runtime.charge.strategy.main",
    provenance="accepted AGM four-step charge program",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
)

AGM_PLATEAU_REQUIRED_MINUTES = VariableSpec(
    key="charge.main.agm_plateau_required_minutes",
    default=120.0,
    value_type=float,
    unit="min",
    description="Required AGM persistent MAIN plateau duration for first-stage evidence.",
    owner="runtime.charge.strategy.main",
    provenance="accepted AGM plateau evidence rule",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=1440.0,
)

STANDARD_PLATEAU_REQUIRED_MINUTES = VariableSpec(
    key="charge.main.standard_plateau_required_minutes",
    default=40.0,
    value_type=float,
    unit="min",
    description="Required Ca/Ca, EFB and flooded persistent MAIN plateau duration.",
    owner="runtime.charge.strategy.main",
    provenance="accepted production plateau evidence rule",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=1440.0,
)

NEAR_TARGET_MARGIN_V = VariableSpec(
    key="charge.main.near_target_margin_v",
    default=0.20,
    value_type=float,
    unit="V",
    description="Voltage margin below the MAIN target considered near-target for plateau evidence.",
    owner="runtime.charge.strategy.main",
    provenance="accepted first-stage evidence rule",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0.0,
    maximum=2.0,
)

PLATEAU_EVIDENCE_WINDOW_MINUTES = VariableSpec(
    key="charge.main.plateau_evidence_window_minutes",
    default=15.0,
    value_type=float,
    unit="min",
    description="Evidence window already represented by CURRENT_PLATEAU when its clock starts.",
    owner="runtime.charge.strategy.main",
    provenance="signal analyzer CURRENT_PLATEAU window",
    override_policy=OverridePolicy.CODE_DEFAULT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=0.0,
    maximum=240.0,
)


def main_fallback_seconds() -> float:
    return float(MAIN_FALLBACK_HOURS.default) * 3600.0


def standard_tail_hold_seconds() -> float:
    return float(STANDARD_TAIL_HOLD_HOURS.default) * 3600.0


def agm_tail_hold_seconds() -> float:
    return float(AGM_TAIL_HOLD_HOURS.default) * 3600.0


__all__ = [
    "AGM_MAX_RECOVERY_ATTEMPTS",
    "CA_MAIN_VOLTAGE_V",
    "DEFAULT_MAIN_VOLTAGE_V",
    "EFB_MAIN_VOLTAGE_V",
    "MAIN_CURRENT_C_RATE",
    "AGM_PLATEAU_REQUIRED_MINUTES",
    "AGM_STAGE_VOLTAGES_V",
    "AGM_TAIL_HOLD_HOURS",
    "AGM_TIMEOUT_TAIL_CURRENT_A",
    "MAIN_FALLBACK_HOURS",
    "NEAR_TARGET_MARGIN_V",
    "PLATEAU_EVIDENCE_WINDOW_MINUTES",
    "STANDARD_MAX_RECOVERY_ATTEMPTS",
    "STANDARD_PLATEAU_REQUIRED_MINUTES",
    "STANDARD_TAIL_HOLD_HOURS",
    "agm_tail_hold_seconds",
    "main_fallback_seconds",
    "standard_tail_hold_seconds",
]
