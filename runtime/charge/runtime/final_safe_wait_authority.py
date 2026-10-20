"""Build the verified Storage request for final SAFE_WAIT."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional

from runtime.charge.strategy.final_safe_wait import (
    FinalSafeWaitAction,
    FinalSafeWaitContinuation,
    FinalSafeWaitDecision,
    decide_final_safe_wait,
    validate_final_continuation,
)


def apply_final_safe_wait_authority(
    host,
    *,
    now: float,
    voltage: float,
    current: float,
    temp: float,
    ah: float,
    actions: dict,
    output_is_on,
):
    """Own final SAFE_WAIT validation, request construction, and dispatch."""
    from runtime.charge.decisions import AuthorityAction, AuthorityDecision
    from runtime.charge.evidence.trace_context import normalize_output_on
    from runtime.charge.runtime.stop_diagnose import apply_stop_and_diagnose

    output_is_off = normalize_output_on(output_is_on) is False
    if output_is_off:
        host._record_safe_wait_sample(now, voltage, current, temp)
    effect = build_final_safe_wait_authority_effect(
        host._final_safe_wait,
        current_stage=host.current_stage,
        safe_wait_stage=host.STAGE_SAFE_WAIT,
        done_stage=host.STAGE_DONE,
        session_id=host._v2_trace_session_id,
        session_generation=host._v2_trace_started_at,
        allowed_source_stages={host.STAGE_MAIN, host.STAGE_MIX},
        now_s=now,
        voltage_v=voltage,
        output_is_off=output_is_off,
        add_phase_limits=host._add_phase_limits,
    )
    if effect is None:
        reason = "final_safe_wait_continuation_invalid"
        apply_stop_and_diagnose(
            host, actions=actions, now=now, voltage=voltage,
            current=current, temp=temp, ah=ah, reason=reason,
        )
        host._final_safe_wait = None
        return AuthorityDecision(AuthorityAction.STOP_AND_DIAGNOSE, reason)
    actions.update(effect.actions)
    decision = effect.decision
    if decision.action == FinalSafeWaitAction.WAIT:
        return AuthorityDecision(AuthorityAction.CONTINUE, decision.reason)
    logging.getLogger("rd6018.recovery").info(
        "V2 final SAFE_WAIT enable attempt reason=%s elapsed=%.1fs",
        decision.reason,
        decision.wait_elapsed_s,
    )
    return AuthorityDecision(
        AuthorityAction.CONTINUE,
        f"final_safe_wait_storage_enable_requested:{decision.reason}",
    )


@dataclass(frozen=True)
class FinalSafeWaitAuthorityEffect:
    decision: FinalSafeWaitDecision
    actions: Mapping[str, object]


def build_final_safe_wait_authority_effect(
    continuation: Optional[FinalSafeWaitContinuation],
    *,
    current_stage: str,
    safe_wait_stage: str,
    done_stage: str,
    session_id: Optional[str],
    session_generation: Optional[float],
    allowed_source_stages: set[str],
    now_s: float,
    voltage_v: float,
    output_is_off: bool,
    add_phase_limits,
) -> Optional[FinalSafeWaitAuthorityEffect]:
    """Validate the continuation, decide relaxation, and assemble its request."""
    if continuation is None or current_stage != safe_wait_stage or not validate_final_continuation(
        continuation,
        session_id=session_id,
        session_generation=session_generation,
        expected_next_stage=done_stage,
        allowed_source_stages=allowed_source_stages,
    ):
        return None

    decision = decide_final_safe_wait(
        continuation,
        now_s=now_s,
        voltage_v=voltage_v,
        output_is_off=output_is_off,
    )
    actions: dict[str, object] = {}
    if decision.action == FinalSafeWaitAction.REQUEST_STORAGE_ENABLE:
        actions["set_voltage"] = continuation.target_voltage_v
        actions["set_current"] = continuation.target_current_a
        add_phase_limits(actions, continuation.target_voltage_v, continuation.target_current_a)
        actions["turn_on"] = True
        actions["verified_enable_transition"] = {
            "kind": "final_safe_wait_to_done",
            "session_id": continuation.session_id,
            "session_generation": continuation.session_generation,
            "started_at": continuation.started_at,
            "reason": decision.reason,
        }
        actions["log_event"] = "FINAL_SAFE_WAIT_STORAGE_ENABLE_ATTEMPT"
    return FinalSafeWaitAuthorityEffect(decision, MappingProxyType(actions))


__all__ = [
    "FinalSafeWaitAuthorityEffect",
    "apply_final_safe_wait_authority",
    "build_final_safe_wait_authority_effect",
]
