"""Module-owned safety limits being migrated out of the historical controller."""

from __future__ import annotations

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec


MAX_STAGE_CURRENT_A = VariableSpec(
    key="safety.max_stage_current_a",
    default=12.0,
    value_type=float,
    unit="A",
    description="Hard software ceiling for automatic and manual RD6018 stage current.",
    owner="runtime.safety",
    provenance="accepted production hard stage-current limit",
    override_policy=OverridePolicy.DEPLOYMENT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=0.1,
    maximum=18.0,
)


PROTECTION_OVP_MARGIN_V = VariableSpec(
    key="safety.protection.ovp_margin_v",
    default=0.1,
    value_type=float,
    unit="V",
    description="Required OVP headroom above a programmed target voltage.",
    owner="runtime.safety",
    provenance="accepted production OVP target margin",
    override_policy=OverridePolicy.DEPLOYMENT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=0.0,
    maximum=2.0,
)

PROTECTION_OCP_MARGIN_A = VariableSpec(
    key="safety.protection.ocp_margin_a",
    default=0.1,
    value_type=float,
    unit="A",
    description="Required OCP headroom above a programmed target current.",
    owner="runtime.safety",
    provenance="accepted production OCP target margin",
    override_policy=OverridePolicy.DEPLOYMENT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=0.0,
    maximum=5.0,
)

WATCHDOG_TIMEOUT_S = VariableSpec(
    key="safety.watchdog.timeout_s",
    default=300.0,
    value_type=float,
    unit="s",
    description="Communication watchdog timeout before managed containment.",
    owner="runtime.safety",
    provenance="accepted production five-minute watchdog timeout",
    override_policy=OverridePolicy.DEPLOYMENT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=1.0,
    maximum=3600.0,
)

HIGH_V_FAST_TIMEOUT_S = VariableSpec(
    key="safety.watchdog.high_voltage_fast_timeout_s",
    default=60.0,
    value_type=float,
    unit="s",
    description="Fast communication-loss timeout while measured voltage is above the high-voltage threshold.",
    owner="runtime.safety",
    provenance="accepted production high-voltage watchdog timeout",
    override_policy=OverridePolicy.DEPLOYMENT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=1.0,
    maximum=600.0,
)

HIGH_V_THRESHOLD_V = VariableSpec(
    key="safety.watchdog.high_voltage_threshold_v",
    default=15.0,
    value_type=float,
    unit="V",
    description="Measured-voltage threshold that activates the fast communication watchdog.",
    owner="runtime.safety",
    provenance="accepted production high-voltage watchdog threshold",
    override_policy=OverridePolicy.DEPLOYMENT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=12.0,
    maximum=18.0,
)


__all__ = [
    "HIGH_V_FAST_TIMEOUT_S",
    "HIGH_V_THRESHOLD_V",
    "MAX_STAGE_CURRENT_A",
    "PROTECTION_OCP_MARGIN_A",
    "PROTECTION_OVP_MARGIN_V",
    "WATCHDOG_TIMEOUT_S",
]
