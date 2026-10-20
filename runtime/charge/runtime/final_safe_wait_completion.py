"""Verified final SAFE_WAIT completion commit after the execution transaction."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from runtime.charge.strategy.final_safe_wait import FinalSafeWaitContinuation

logger = logging.getLogger("rd6018.charge.final_safe_wait")


@dataclass(frozen=True)
class FinalSafeWaitCompletionInput:
    continuation: FinalSafeWaitContinuation | None
    current_stage: str
    safe_wait_stage: str
    done_stage: str
    active_session_generation: Any
    transition: Mapping[str, Any]
    now_s: float
    voltage_v: float
    current_a: float
    ah: float


@dataclass(frozen=True)
class FinalSafeWaitCompletionEffect:
    now_s: float
    voltage_v: float
    current_a: float
    ah: float
    stage: str
    source_stage: str
    result: Mapping[str, str]


def build_final_safe_wait_completion_effect(
    value: FinalSafeWaitCompletionInput,
) -> FinalSafeWaitCompletionEffect | None:
    continuation = value.continuation
    if continuation is None or value.current_stage != value.safe_wait_stage:
        return None
    try:
        token_session = str(value.transition.get("session_id") or "") or None
        token_started_at = float(value.transition.get("started_at"))
        token_generation = float(value.transition.get("session_generation"))
        continuation_generation = float(continuation.session_generation)
        active_generation = float(value.active_session_generation)
        now_s, voltage_v = float(value.now_s), float(value.voltage_v)
        current_a, ah = float(value.current_a), float(value.ah)
    except (TypeError, ValueError, OverflowError):
        return None

    if (
        token_session != continuation.session_id
        or continuation.session_generation is None
        or not all(math.isfinite(item) for item in (
            token_started_at, token_generation, continuation_generation,
            active_generation,
        ))
        or abs(token_started_at - continuation.started_at) > 1e-6
        or abs(token_generation - continuation_generation) > 1e-6
        or abs(token_generation - active_generation) > 1e-6
    ):
        logger.error("verified final completion rejected: continuation token mismatch")
        return None

    return FinalSafeWaitCompletionEffect(
        now_s=now_s,
        voltage_v=voltage_v,
        current_a=current_a,
        ah=ah,
        stage=value.done_stage,
        source_stage=value.safe_wait_stage,
        result=MappingProxyType({
            "log_event": "START | V2_STORAGE_OUTPUT_VERIFIED",
            "notify": "<b>✅ Заряд завершён.</b> Storage включён и подтверждён.",
        }),
    )


def apply_final_safe_wait_completion_effect(
    host: Any, effect: FinalSafeWaitCompletionEffect
) -> dict[str, str]:
    """Apply the verified DONE edge and persist its existing Storage intent."""
    host.current_stage = effect.stage
    host._clear_restored_targets()
    host.stage_start_time = effect.now_s
    host._stage_start_ah = effect.ah
    host._safe_wait_next_stage = None
    host._safe_wait_target_v = 0.0
    host._safe_wait_target_i = 0.0
    host._safe_wait_start = 0.0
    host._final_safe_wait = None
    host._recovery_safe_wait = None
    host._save_session(
        effect.voltage_v, effect.current_a, effect.ah,
        verified_storage_completion=True,
    )
    return dict(effect.result)


__all__ = [
    "FinalSafeWaitCompletionEffect",
    "FinalSafeWaitCompletionInput",
    "apply_final_safe_wait_completion_effect",
    "build_final_safe_wait_completion_effect",
]
