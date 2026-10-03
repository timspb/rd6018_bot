"""Authoritative MAIN transition policy.

This module is the canonical owner of MAIN transition semantics. It is pure:
no controller mutation, persistence, UI or physical execution.
"""

from __future__ import annotations

from typing import Any, Optional

from first_stage_evidence import FirstStageAssessment, FirstStageState
from recovery_policy import RecoveryDecision

from runtime.charge.decisions import AuthorityAction, AuthorityDecision
from .main_variables import AGM_TIMEOUT_TAIL_CURRENT_A


AUTOMATIC_HV_INTENTS = frozenset({"normal", "recovery", "conditioning"})
RECOVERY_INTENTS = AUTOMATIC_HV_INTENTS


def _unsafe_policy_decision(decision: RecoveryDecision) -> bool:
    return decision in {
        RecoveryDecision.HOLD_OUTPUT_OFF,
        RecoveryDecision.PAUSE_THERMAL,
        RecoveryDecision.REST_AND_DIAGNOSE,
    }


def decide_main_transition(
    *,
    profile: str,
    intent: Any,
    first_stage: Optional[FirstStageAssessment],
    policy_decision: RecoveryDecision,
    seconds_since_current_min: Optional[float],
    required_tail_hold_s: float,
    agm_stage_idx: int = 0,
    agm_stage_count: int = 1,
    desulf_attempts: int = 0,
    max_desulf_attempts: int = 0,
    high_plateau_c_rate: Optional[float] = None,
    main_elapsed_s: Optional[float] = None,
    main_limit_s: Optional[float] = None,
    current_a: Optional[float] = None,
    is_cv: bool = False,
) -> AuthorityDecision:
    """Choose the authoritative MAIN transition.

    NORMAL preserves the accepted automatic chain including bounded recovery and
    final Mix. DIAGNOSTIC never creates a new automatic HV stage. AGM remains
    conservative when its recovery budget is exhausted.
    """
    _ = high_plateau_c_rate

    if _unsafe_policy_decision(policy_decision):
        return AuthorityDecision(
            AuthorityAction.STOP_AND_DIAGNOSE,
            f"policy_{policy_decision.value}",
        )

    profile_upper = str(profile).strip().upper()
    intent_key = str(getattr(intent, "value", intent)).strip().lower()
    hv_allowed = intent_key in AUTOMATIC_HV_INTENTS

    if (
        main_elapsed_s is not None
        and main_limit_s is not None
        and float(main_elapsed_s) >= float(main_limit_s)
    ):
        if not hv_allowed:
            return AuthorityDecision(
                AuthorityAction.STOP_AND_DIAGNOSE,
                "main_timeout_diagnostic_no_hv",
            )
        if profile_upper in {"CA/CA", "CA", "EFB", "FLOODED"}:
            return AuthorityDecision(
                AuthorityAction.ENTER_MIX,
                "main_timeout_ca_efb_v1_compatible_mix",
            )
        if profile_upper == "AGM":
            current = float(current_a) if current_a is not None else float("inf")
            if bool(is_cv) and current <= float(AGM_TIMEOUT_TAIL_CURRENT_A.default):
                return AuthorityDecision(
                    AuthorityAction.ENTER_MIX,
                    "agm_main_timeout_low_current_cv_mix",
                )
            return AuthorityDecision(
                AuthorityAction.STOP_AND_DIAGNOSE,
                "agm_main_timeout_without_low_current_tail",
            )
        return AuthorityDecision(
            AuthorityAction.STOP_AND_DIAGNOSE,
            "main_timeout_profile_not_hv_authorized",
        )

    if first_stage is None:
        return AuthorityDecision(AuthorityAction.CONTINUE, "main_evidence_not_ready")

    if first_stage.state in {
        FirstStageState.TELEMETRY_INVALID,
        FirstStageState.THERMALLY_UNSTABLE,
        FirstStageState.VOLTAGE_UNSTABLE,
    }:
        return AuthorityDecision(
            AuthorityAction.STOP_AND_DIAGNOSE,
            f"main_{first_stage.state.value}",
        )

    if first_stage.state == FirstStageState.STUCK_PLATEAU:
        if not hv_allowed:
            return AuthorityDecision(
                AuthorityAction.STOP_AND_DIAGNOSE,
                "persistent_main_plateau_diagnostic_no_hv",
            )
        if desulf_attempts < max_desulf_attempts:
            return AuthorityDecision(
                AuthorityAction.ENTER_DESULFATION,
                "moderate_stable_cv_plateau_recovery_evidence",
            )
        if profile_upper == "AGM":
            return AuthorityDecision(
                AuthorityAction.CONTINUE,
                "agm_recovery_budget_exhausted_wait_for_tail",
            )
        return AuthorityDecision(
            AuthorityAction.ENTER_MIX,
            "moderate_plateau_after_desulfation_budget",
        )

    if first_stage.state == FirstStageState.TAIL_READY:
        age = float(seconds_since_current_min or 0.0)
        if age < float(required_tail_hold_s):
            return AuthorityDecision(
                AuthorityAction.CONTINUE,
                "tail_ready_but_hold_not_complete",
            )
        if profile_upper == "AGM" and int(agm_stage_idx) < int(agm_stage_count) - 1:
            return AuthorityDecision(
                AuthorityAction.ADVANCE_AGM_STEP,
                "agm_tail_hold_complete_advance_voltage_step",
            )
        if hv_allowed:
            return AuthorityDecision(
                AuthorityAction.ENTER_MIX,
                "main_tail_hold_complete_standard_mix",
            )
        return AuthorityDecision(
            AuthorityAction.COMPLETE_TO_SAFE_WAIT,
            "main_tail_hold_complete_diagnostic_no_hv",
        )

    return AuthorityDecision(AuthorityAction.CONTINUE, "main_bulk_or_taper_continues")


__all__ = [
    "AUTOMATIC_HV_INTENTS",
    "RECOVERY_INTENTS",
    "decide_main_transition",
]
