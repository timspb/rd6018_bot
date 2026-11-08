"""Module-owned communication-loss notification safety values."""

from __future__ import annotations

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec


LINK_LOSS_INITIAL_NOTICE_COUNT = VariableSpec(
    key="safety.communication.link_loss_initial_notice_count",
    default=2,
    value_type=int,
    unit="count",
    description="Immediate operator notices allowed before communication-loss notifications become rate-limited.",
    owner="runtime.safety.communication",
    provenance="accepted production communication-loss notification policy",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=0,
    maximum=20,
)

LINK_LOSS_NOTICE_INTERVAL_S = VariableSpec(
    key="safety.communication.link_loss_notice_interval_s",
    default=3600.0,
    value_type=float,
    unit="s",
    description="Minimum interval between repeated communication-loss notices after the initial burst.",
    owner="runtime.safety.communication",
    provenance="accepted production communication-loss notification policy",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=60.0,
    maximum=86400.0,
)


SOFT_WATCHDOG_POLL_S = VariableSpec(
    key="safety.watchdog.soft_poll_s",
    default=10.0,
    value_type=float,
    unit="s",
    description="Polling cadence of the canonical software-watchdog policy.",
    owner="runtime.safety",
    provenance="accepted production 10-second soft watchdog loop",
    override_policy=OverridePolicy.DEPLOYMENT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=1.0,
    maximum=60.0,
)

COMMUNICATION_WATCHDOG_POLL_S = VariableSpec(
    key="safety.watchdog.communication_poll_s",
    default=30.0,
    value_type=float,
    unit="s",
    description="Polling cadence of the managed communication watchdog.",
    owner="runtime.safety",
    provenance="accepted production 30-second communication watchdog loop",
    override_policy=OverridePolicy.DEPLOYMENT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=1.0,
    maximum=120.0,
)


__all__ = [
    "LINK_LOSS_INITIAL_NOTICE_COUNT", "LINK_LOSS_NOTICE_INTERVAL_S",
    "SOFT_WATCHDOG_POLL_S", "COMMUNICATION_WATCHDOG_POLL_S",
]
