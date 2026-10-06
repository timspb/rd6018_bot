"""Pure recovery SAFE_WAIT continuation and decision owner."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from runtime.charge.strategy.safe_wait_variables import (
    SAFE_WAIT_TARGET_MARGIN_V,
    safe_wait_max_seconds,
)


@dataclass(frozen=True)
class RecoverySafeWaitContinuation:
    source_stage: str
    next_stage: str
    target_voltage_v: float
    target_current_a: float
    started_at: float
    session_id: Optional[str]
    recovery_attempt: int
    agm_stage_idx: int
    session_generation: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "version": 2,
            "source_stage": self.source_stage,
            "next_stage": self.next_stage,
            "target_voltage_v": self.target_voltage_v,
            "target_current_a": self.target_current_a,
            "started_at": self.started_at,
            "session_id": self.session_id,
            "session_generation": self.session_generation,
            "recovery_attempt": self.recovery_attempt,
            "agm_stage_idx": self.agm_stage_idx,
        }


class RecoverySafeWaitAction(str, Enum):
    WAIT = "wait"
    REQUEST_MAIN_ENABLE = "request_main_enable"
    REJECT = "reject"


@dataclass(frozen=True)
class RecoverySafeWaitDecision:
    action: RecoverySafeWaitAction
    reason: str
    wait_elapsed_s: float
    threshold_v: float


def validate_recovery_continuation(
    continuation: RecoverySafeWaitContinuation,
    *,
    session_id: Optional[str],
    session_generation: Optional[float],
    expected_source_stage: str,
    expected_next_stage: str,
) -> bool:
    if continuation.source_stage != expected_source_stage:
        return False
    if continuation.next_stage != expected_next_stage:
        return False
    if not math.isfinite(float(continuation.target_voltage_v)) or continuation.target_voltage_v <= 0:
        return False
    if not math.isfinite(float(continuation.target_current_a)) or continuation.target_current_a <= 0:
        return False
    if not math.isfinite(float(continuation.started_at)) or continuation.started_at <= 0:
        return False
    if not continuation.session_id or not session_id:
        return False
    if continuation.session_id != session_id:
        return False
    if continuation.session_generation is None or session_generation is None:
        return False
    try:
        generation = float(session_generation)
        saved_generation = float(continuation.session_generation)
    except (TypeError, ValueError, OverflowError):
        return False
    if not math.isfinite(generation) or not math.isfinite(saved_generation):
        return False
    if abs(saved_generation - generation) > 1e-6:
        return False
    return True


def decide_recovery_safe_wait(
    continuation: RecoverySafeWaitContinuation,
    *,
    now_s: float,
    voltage_v: float,
    output_is_off: bool,
) -> RecoverySafeWaitDecision:
    threshold = float(continuation.target_voltage_v) - float(SAFE_WAIT_TARGET_MARGIN_V.default)
    wait_elapsed = max(0.0, float(now_s) - float(continuation.started_at))
    if not output_is_off:
        return RecoverySafeWaitDecision(
            RecoverySafeWaitAction.WAIT,
            "fresh_output_off_required",
            wait_elapsed,
            threshold,
        )
    if float(voltage_v) <= threshold:
        return RecoverySafeWaitDecision(
            RecoverySafeWaitAction.REQUEST_MAIN_ENABLE,
            "threshold",
            wait_elapsed,
            threshold,
        )
    if wait_elapsed + 1e-6 >= safe_wait_max_seconds():
        return RecoverySafeWaitDecision(
            RecoverySafeWaitAction.REQUEST_MAIN_ENABLE,
            "timeout",
            wait_elapsed,
            threshold,
        )
    return RecoverySafeWaitDecision(
        RecoverySafeWaitAction.WAIT,
        "relaxation_in_progress",
        wait_elapsed,
        threshold,
    )


__all__ = [
    "RecoverySafeWaitAction",
    "RecoverySafeWaitContinuation",
    "RecoverySafeWaitDecision",
    "decide_recovery_safe_wait",
    "validate_recovery_continuation",
]
