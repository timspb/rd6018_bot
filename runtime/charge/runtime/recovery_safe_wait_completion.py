"""Verified recovery SAFE_WAIT resume commit after Output ON readback."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from runtime.charge.runtime.variables import STAGE_TRANSITION_BLANKING_S

logger = logging.getLogger("rd6018.charge.recovery_runtime")


@dataclass(frozen=True)
class RecoverySafeWaitCompletionInput:
    continuation: Any
    current_stage: str
    safe_wait_stage: str
    active_session_generation: Any
    transition: Mapping[str, Any]
    now_s: float
    voltage_v: float
    current_a: float
    ah: float


@dataclass(frozen=True)
class RecoverySafeWaitCompletionEffect:
    now_s: float
    voltage_v: float
    current_a: float
    ah: float
    next_stage: str
    blanking_seconds: float
    reason: str
    target_voltage_v: float
    result: Mapping[str, str]


def build_recovery_safe_wait_completion_effect(
    value: RecoverySafeWaitCompletionInput,
) -> RecoverySafeWaitCompletionEffect | None:
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
            active_generation, now_s, voltage_v, current_a, ah,
        ))
        or abs(token_started_at - continuation.started_at) > 1e-6
        or abs(token_generation - continuation_generation) > 1e-6
        or abs(token_generation - active_generation) > 1e-6
    ):
        logger.error("verified recovery resume rejected: continuation token mismatch")
        return None

    reason = str(value.transition.get("reason") or "verified_enable")
    timeout = reason == "timeout"
    return RecoverySafeWaitCompletionEffect(
        now_s=now_s,
        voltage_v=voltage_v,
        current_a=current_a,
        ah=ah,
        next_stage=str(continuation.next_stage),
        blanking_seconds=float(STAGE_TRANSITION_BLANKING_S.default),
        reason=reason,
        target_voltage_v=float(continuation.target_voltage_v),
        result=MappingProxyType({
            "log_event": (
                "START | RECOVERY_SAFE_WAIT_TIMEOUT_TO_MAIN" if timeout
                else "START | RECOVERY_SAFE_WAIT_TO_MAIN"
            ),
            "notify": (
                "?? ?????????? ?????? ???????? ????? ?????????? ?????. "
                f"????? ????????????? ???????? ??????????? ??????? ? Main "
                f"({float(continuation.target_voltage_v):.1f}?)." if timeout
                else "<b>?? ??????? ? Main Charge ???????????.</b> Output ??????? ? ??????? ?????????."
            ),
        }),
    )


def apply_recovery_safe_wait_completion_effect(
    host: Any, effect: RecoverySafeWaitCompletionEffect,
) -> dict[str, str]:
    """Apply and persist the pre-existing recovery continuation commit."""
    previous = host.current_stage
    host.current_stage = effect.next_stage
    host._clear_restored_targets()
    host.stage_start_time = effect.now_s
    host._stage_start_ah = effect.ah
    host._blanking_until = effect.now_s + effect.blanking_seconds
    host.v_max_recorded = None
    host.i_min_recorded = None
    host._delta_trigger_count = 0
    host._main_sample_evidence.reset()
    host._safe_wait_next_stage = None
    host._safe_wait_target_v = 0.0
    host._safe_wait_target_i = 0.0
    host._safe_wait_start = 0.0
    host._recovery_safe_wait = None
    host._log_stage_transition(
        old_stage=previous,
        new_stage=host.current_stage,
        timestamp_s=effect.now_s,
        reason=f"recovery_safe_wait_verified_enable:{effect.reason}",
    )
    host._save_session(effect.voltage_v, effect.current_a, effect.ah)
    logger.info(
        "V2 recovery SAFE_WAIT -> %s committed after verified Output ON reason=%s",
        host.current_stage, effect.reason,
    )
    return dict(effect.result)


__all__ = [
    "RecoverySafeWaitCompletionEffect",
    "RecoverySafeWaitCompletionInput",
    "apply_recovery_safe_wait_completion_effect",
    "build_recovery_safe_wait_completion_effect",
]
