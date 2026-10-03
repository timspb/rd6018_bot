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


__all__ = ["MAX_STAGE_CURRENT_A"]
