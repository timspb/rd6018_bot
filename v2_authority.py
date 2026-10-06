"""Compatibility surface for charge authority decisions.

MAIN and MIX decisions are owned by modular charge strategy modules. This file
keeps historical imports/call signatures only for transitional callers/tests.
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
from runtime.charge.strategy.main_variables import (
    AGM_TIMEOUT_TAIL_CURRENT_A as _AGM_TIMEOUT_TAIL_CURRENT_A,
)
from runtime.charge.strategy.mix import decide_mix_transition as _decide_mix_transition


AGM_TIMEOUT_TAIL_CURRENT_A = float(_AGM_TIMEOUT_TAIL_CURRENT_A.default)


def decide_mix_transition(
    *,
    policy_decision: RecoveryDecision,
    mix_elapsed_s: float,
    mix_limit_s: float,
    finish_hold_started_at: Optional[float],
    now_s: float,
    finish_hold_s: float,
) -> AuthorityDecision:
    """Compatibility adapter over the canonical modular MIX decision."""

    return _decide_mix_transition(
        profile="compat",
        policy_decision=policy_decision,
        active_elapsed_s=float(mix_elapsed_s),
        finish_hold_started_at=finish_hold_started_at,
        now_s=float(now_s),
        authority_limit_s=float(mix_limit_s),
        finish_hold_s=float(finish_hold_s),
    )


__all__ = [
    "AGM_TIMEOUT_TAIL_CURRENT_A",
    "AUTOMATIC_HV_INTENTS",
    "AuthorityAction",
    "AuthorityDecision",
    "RECOVERY_INTENTS",
    "decide_main_transition",
    "decide_mix_transition",
]
