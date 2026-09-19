"""Read-only V2/V3 decision parity contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from application.charge_engine.models import TelemetrySnapshot


class ShadowParityStatus(str, Enum):
    MATCH = "MATCH"
    EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
    DIVERGENCE = "DIVERGENCE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ShadowDecisionInput:
    telemetry: TelemetrySnapshot | None
    battery_profile: str
    current_phase: str
    current_program: str
    lifecycle_state: str
    session_id: str = ""
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        for name in ("battery_profile", "current_phase", "current_program", "lifecycle_state"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if self.timestamp < 0:
            raise ValueError("timestamp cannot be negative")


@dataclass(frozen=True)
class ShadowDecisionView:
    selected_program: str | None
    phase: str | None
    target_voltage_v: float | None
    target_current_a: float | None
    safety_result: str | None
    execution_intent: tuple[tuple[str, Any], ...] | None


@dataclass(frozen=True)
class ShadowDivergence:
    field: str
    timestamp: float
    session_id: str
    reason: str
    source_owner: str
    v2_value: Any
    v3_value: Any


@dataclass(frozen=True)
class ShadowDecisionComparison:
    status: ShadowParityStatus
    timestamp: float
    session_id: str
    divergences: tuple[ShadowDivergence, ...]


def _safety_value(value: Any) -> Any:
    if value is None:
        return None
    return getattr(value, "state", value)


class ShadowDecisionParityEngine:
    """Compare decisions without mutating either decision owner."""

    FIELDS = (
        "selected_program",
        "phase",
        "target_voltage_v",
        "target_current_a",
        "safety_result",
        "execution_intent",
    )

    def compare(
        self,
        context: ShadowDecisionInput,
        v2: ShadowDecisionView,
        v3: ShadowDecisionView,
        *,
        expected_fields: tuple[str, ...] = (),
    ) -> ShadowDecisionComparison:
        missing = context.telemetry is None or not context.telemetry.complete
        divergences: list[ShadowDivergence] = []
        for field in self.FIELDS:
            left = _safety_value(getattr(v2, field)) if field == "safety_result" else getattr(v2, field)
            right = _safety_value(getattr(v3, field)) if field == "safety_result" else getattr(v3, field)
            if left == right:
                continue
            status_reason = "known model difference" if field in expected_fields else "V2/V3 decision values differ"
            divergences.append(
                ShadowDivergence(
                    field, context.timestamp, context.session_id, status_reason,
                    "V2 vs V3 observer comparison", left, right,
                )
            )
        if missing:
            status = ShadowParityStatus.UNKNOWN
        elif not divergences:
            status = ShadowParityStatus.MATCH
        elif all(item.field in expected_fields for item in divergences):
            status = ShadowParityStatus.EXPECTED_DIFFERENCE
        else:
            status = ShadowParityStatus.DIVERGENCE
        return ShadowDecisionComparison(status, context.timestamp, context.session_id, tuple(divergences))


__all__ = [
    "ShadowDecisionInput",
    "ShadowDecisionParityEngine",
    "ShadowDecisionView",
    "ShadowDecisionComparison",
    "ShadowDivergence",
    "ShadowParityStatus",
]
