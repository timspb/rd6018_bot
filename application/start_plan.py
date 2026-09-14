"""Immutable approved START plan; it contains no execution dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from pb_domain import BatteryIdentity

from .start_request import StartPreflightResult, TargetPreview


@dataclass(frozen=True)
class ApprovedStartPlan:
    """The read-only handoff from START preflight to a future runtime service."""

    profile: str
    chemistry: str
    recipe_id: str
    target_preview: TargetPreview
    current_limit_preview_a: float
    battery_identity: BatteryIdentity
    ownership_result: str
    safety_result: str
    telemetry_evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.profile or not self.chemistry or not self.recipe_id:
            raise ValueError("approved plan identity is incomplete")
        if self.current_limit_preview_a < 0:
            raise ValueError("current limit preview must be >= 0")
        object.__setattr__(self, "telemetry_evidence", MappingProxyType(dict(self.telemetry_evidence)))


@dataclass(frozen=True)
class StartPlanComparison:
    status: str
    fields: tuple[str, ...] = ()
    v2: Mapping[str, Any] = field(default_factory=dict)
    v3: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""


def approved_plan_from_preflight(result: StartPreflightResult) -> ApprovedStartPlan:
    """Convert only an allowed preflight result; never performs execution."""
    if not result.allowed:
        raise ValueError("cannot create an approved plan from denied preflight")
    if result.recipe_preview is None or result.target_preview is None:
        raise ValueError("approved preflight is missing recipe or target preview")
    if result.battery_identity is None:
        raise ValueError("approved preflight is missing battery identity")
    return ApprovedStartPlan(
        profile=result.profile,
        chemistry=result.chemistry,
        recipe_id=result.recipe_preview.recipe_id,
        target_preview=result.target_preview,
        current_limit_preview_a=result.target_preview.current_a,
        battery_identity=result.battery_identity,
        ownership_result=result.ownership_status,
        safety_result=result.safety_status,
        telemetry_evidence=result.telemetry_evidence,
    )


def compare_approved_start_plan(
    v2: Mapping[str, Any],
    plan: ApprovedStartPlan,
) -> StartPlanComparison:
    """Compare captured V2 expected values with a non-executing V3 plan."""
    v3 = {
        "profile": plan.profile,
        "chemistry": plan.chemistry,
        "recipe_id": plan.recipe_id,
        "target_voltage_v": plan.target_preview.voltage_v,
        "target_current_a": plan.target_preview.current_a,
        "current_limit_preview_a": plan.current_limit_preview_a,
        "ownership_status": plan.ownership_result,
        "safety_status": plan.safety_result,
    }
    fields = tuple(sorted(key for key in set(v2) | set(v3) if v2.get(key) != v3.get(key)))
    return StartPlanComparison("MATCH" if not fields else "MISMATCH", fields, dict(v2), v3)
