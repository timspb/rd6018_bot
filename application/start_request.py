"""Data-only request and preview models for a future START command."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from pb_domain import BatteryCondition, BatteryIdentity, ChargeIntent
from recipe_engine import RecipeEnvelope


@dataclass(frozen=True)
class StartRequest:
    profile: str
    capacity_ah: float
    battery_identity: BatteryIdentity | None = None
    battery_id: str = "operator-battery"
    intent: ChargeIntent = ChargeIntent.NORMAL
    condition: BatteryCondition = BatteryCondition.UNKNOWN
    operator: str = ""
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.profile).strip():
            raise ValueError("profile is required")
        if float(self.capacity_ah) <= 0:
            raise ValueError("capacity_ah must be > 0")
        if not str(self.operator).strip():
            raise ValueError("operator is required")


@dataclass(frozen=True)
class TargetPreview:
    voltage_v: float
    current_a: float
    stage: str
    prep_skipped: bool


@dataclass(frozen=True)
class StartPreflightResult:
    allowed: bool
    reasons: tuple[str, ...] = ()
    ownership_status: str = "unknown"
    telemetry_status: str = "unknown"
    safety_status: str = "unknown"
    recipe_preview: RecipeEnvelope | None = None
    target_preview: TargetPreview | None = None
    profile: str = ""
    chemistry: str = ""
    battery_identity: BatteryIdentity | None = None
    telemetry_evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StartPreflightComparison:
    status: str
    fields: tuple[str, ...] = ()
    v2: Mapping[str, Any] = field(default_factory=dict)
    v3: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""
