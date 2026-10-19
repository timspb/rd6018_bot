"""Build the verified Storage request for final SAFE_WAIT."""

from __future__ import annotations

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


__all__ = ["FinalSafeWaitAuthorityEffect", "build_final_safe_wait_authority_effect"]
