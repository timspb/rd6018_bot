"""Compatibility surface for charge authority decisions.

MAIN authority is owned by the modular charge strategy. MIX remains here until
its own migration boundary is completed.
"""

from __future__ import annotations

from typing import Optional

from recovery_policy import RecoveryDecision
from runtime.charge.decisions import AuthorityAction, AuthorityDecision
from runtime.charge.strategy.main_authority import (
    AUTOMATIC_HV_INTENTS,
    RECOVERY_INTENTS,
    decide_main_transition,
)
from runtime.charge.strategy.main_variables import AGM_TIMEOUT_TAIL_CURRENT_A as _AGM_TIMEOUT_TAIL_CURRENT_A


# Compatibility value for older tests/importers. The semantic owner is
# runtime.charge.strategy.main_variables.
AGM_TIMEOUT_TAIL_CURRENT_A = float(_AGM_TIMEOUT_TAIL_CURRENT_A.default)


def _unsafe_policy_decision(decision: RecoveryDecision) -> bool:
    return decision in {
        RecoveryDecision.HOLD_OUTPUT_OFF,
        RecoveryDecision.PAUSE_THERMAL,
        RecoveryDecision.REST_AND_DIAGNOSE,
    }


def decide_mix_transition(
    *,
    policy_decision: RecoveryDecision,
    mix_elapsed_s: float,
    mix_limit_s: float,
    finish_hold_started_at: Optional[float],
    now_s: float,
    finish_hold_s: float,
) -> AuthorityDecision:
    if _unsafe_policy_decision(policy_decision):
        return AuthorityDecision(
            AuthorityAction.STOP_AND_DIAGNOSE,
            f"policy_{policy_decision.value}",
        )
    if finish_hold_started_at is not None:
        held = max(0.0, float(now_s) - float(finish_hold_started_at))
        if held >= float(finish_hold_s):
            return AuthorityDecision(
                AuthorityAction.COMPLETE_TO_SAFE_WAIT,
                "confirmed_delta_finish_hold_complete",
            )
        return AuthorityDecision(
            AuthorityAction.CONTINUE,
            "confirmed_delta_finish_hold_running",
        )
    if policy_decision == RecoveryDecision.FINISH_STAGE:
        return AuthorityDecision(
            AuthorityAction.START_FINISH_HOLD,
            "mode_specific_end_of_charge_evidence_confirmed",
        )
    if float(mix_elapsed_s) >= float(mix_limit_s):
        return AuthorityDecision(
            AuthorityAction.STOP_AND_DIAGNOSE,
            "MIX_TIMEOUT",
        )
    return AuthorityDecision(AuthorityAction.CONTINUE, "mix_observation_continues")


__all__ = [
    "AGM_TIMEOUT_TAIL_CURRENT_A",
    "AUTOMATIC_HV_INTENTS",
    "AuthorityAction",
    "AuthorityDecision",
    "RECOVERY_INTENTS",
    "decide_main_transition",
    "decide_mix_transition",
]
