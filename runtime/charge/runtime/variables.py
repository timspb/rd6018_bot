"""Module-owned timing values for charge runtime mechanics."""

from __future__ import annotations

from runtime.config.variable_spec import ChangeEffect, OverridePolicy, VariableSpec


HISTORY_SAMPLE_INTERVAL_S = VariableSpec(
    key="charge.runtime.history_sample_interval_s",
    default=60.0,
    value_type=float,
    unit="s",
    description="Minimum interval between retained V/I history samples.",
    owner="runtime.charge.runtime",
    provenance="accepted production V/I history cadence",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=1.0,
    maximum=3600.0,
)

STAGE_CLOCK_SANITY_MAX_HOURS = VariableSpec(
    key="charge.runtime.stage_clock_sanity_max_hours",
    default=1000.0,
    value_type=float,
    unit="h",
    description="Maximum plausible stage elapsed time before a corrupted/reversed stage clock is reset.",
    owner="runtime.charge.runtime",
    provenance="accepted production stage-clock sanity guard",
    override_policy=OverridePolicy.CODE_DEFAULT_ONLY,
    change_effect=ChangeEffect.DEPLOY_REQUIRED,
    minimum=24.0,
    maximum=10000.0,
)

OPERATOR_REPORT_INTERVAL_S = VariableSpec(
    key="charge.runtime.operator_report_interval_s",
    default=3600.0,
    value_type=float,
    unit="s",
    description="Cadence for periodic active-stage operator reports.",
    owner="runtime.charge.runtime",
    provenance="accepted production hourly stage report cadence",
    override_policy=OverridePolicy.CONFIG_FILE,
    change_effect=ChangeEffect.RESTART_REQUIRED,
    minimum=60.0,
    maximum=86400.0,
)


__all__ = [
    "HISTORY_SAMPLE_INTERVAL_S",
    "OPERATOR_REPORT_INTERVAL_S",
    "STAGE_CLOCK_SANITY_MAX_HOURS",
]
