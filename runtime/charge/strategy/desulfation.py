"""Pure bounded intermediate DESULFATION strategy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from runtime.charge.strategy.desulfation_variables import (
    DESULFATION_BASE_VOLTAGE_V,
    DESULFATION_CURRENT_C_RATE,
    DESULFATION_MIN_CURRENT_A,
    desulfation_duration_seconds,
)
from runtime.safety.variables import MAX_STAGE_CURRENT_A


class DesulfationAction(str, Enum):
    CONTINUE = "continue"
    COMPLETE_TO_SAFE_WAIT = "complete_to_safe_wait"


@dataclass(frozen=True)
class DesulfationDecision:
    action: DesulfationAction
    reason: str


@dataclass(frozen=True)
class DesulfationTarget:
    voltage_v: float
    current_a: float


def select_desulfation_target(*, capacity_ah: float) -> DesulfationTarget:
    capacity = max(1.0, float(capacity_ah))
    current = max(
        float(DESULFATION_MIN_CURRENT_A.default),
        capacity * float(DESULFATION_CURRENT_C_RATE.default),
    )
    current = min(current, float(MAX_STAGE_CURRENT_A.default))
    return DesulfationTarget(
        voltage_v=float(DESULFATION_BASE_VOLTAGE_V.default),
        current_a=current,
    )


def decide_desulfation(*, active_elapsed_s: float) -> DesulfationDecision:
    elapsed = max(0.0, float(active_elapsed_s))
    if elapsed + 1e-6 < desulfation_duration_seconds():
        return DesulfationDecision(
            DesulfationAction.CONTINUE,
            "bounded_intermediate_recovery_active",
        )
    return DesulfationDecision(
        DesulfationAction.COMPLETE_TO_SAFE_WAIT,
        "bounded_intermediate_recovery_complete",
    )


__all__ = [
    "DesulfationAction",
    "DesulfationDecision",
    "DesulfationTarget",
    "decide_desulfation",
    "select_desulfation_target",
]
