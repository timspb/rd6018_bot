from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from first_stage_evidence import FirstStageAssessment, FirstStageState
from pb_domain import ChargeIntent
from recovery_policy import RecoveryDecision


class AuthorityAction(str, Enum):
    CONTINUE = "continue"
    ADVANCE_AGM_STEP = "advance_agm_step"
    ENTER_DESULFATION = "enter_desulfation"
    ENTER_MIX = "enter_mix"
    START_FINISH_HOLD = "start_finish_hold"
    COMPLETE_TO_SAFE_WAIT = "complete_to_safe_wait"
    STOP_AND_DIAGNOSE = "stop_and_diagnose"


@dataclass(frozen=True)
class AuthorityDecision:
    action: AuthorityAction
    reason: str


RECOVERY_INTENTS = frozenset({ChargeIntent.RECOVERY, ChargeIntent.CONDITIONING})


def _unsafe_policy_decision(decision: RecoveryDecision) -> bool:
    return decision in {
        RecoveryDecision.HOLD_OUTPUT_OFF,
        RecoveryDecision.PAUSE_THERMAL,
        RecoveryDecision.REST_AND_DIAGNOSE,
    }


def decide_main_transition(
    *,
    profile: str,
    intent: ChargeIntent,
    first_stage: Optional[FirstStageAssessment],
    policy_decision: RecoveryDecision,
    seconds_since_current_min: Optional[float],
    required_tail_hold_s: float,
    agm_stage_idx: int = 0,
    agm_stage_count: int = 1,
    desulf_attempts: int = 0,
    max_desulf_attempts: int = 0,
    high_plateau_c_rate: Optional[float] = None,
) -> AuthorityDecision:
    """Choose Main transition from evidence and a session-wide recovery budget.

    Current magnitude alone is not a diagnosis of a structural battery fault, so an
    arbitrary C-rate does not veto a confirmed stuck-current recovery cycle. Structural
    HV veto belongs to the diagnostic hypothesis engine where independent evidence can
    be combined. ``high_plateau_c_rate`` is retained only for replay/API compatibility.
    """
    _ = high_plateau_c_rate

    if _unsafe_policy_decision(policy_decision):
        return AuthorityDecision(AuthorityAction.STOP_AND_DIAGNOSE, f"policy_{policy_decision.value}")
    if first_stage is None:
        return AuthorityDecision(AuthorityAction.CONTINUE, "main_evidence_not_ready")
    if first_stage.state in {
        FirstStageState.TELEMETRY_INVALID,
        FirstStageState.THERMALLY_UNSTABLE,
        FirstStageState.VOLTAGE_UNSTABLE,
    }:
        return AuthorityDecision(AuthorityAction.STOP_AND_DIAGNOSE, f"main_{first_stage.state.value}")

    if first_stage.state == FirstStageState.STUCK_PLATEAU:
        if intent not in RECOVERY_INTENTS:
            return AuthorityDecision(
                AuthorityAction.STOP_AND_DIAGNOSE,
                "persistent_main_plateau_requires_recovery_intent",
            )
        if desulf_attempts < max_desulf_attempts:
            return AuthorityDecision(
                AuthorityAction.ENTER_DESULFATION,
                "moderate_stable_cv_plateau_recovery_evidence",
            )
        return AuthorityDecision(
            AuthorityAction.ENTER_MIX,
            "moderate_plateau_after_desulfation_budget",
        )

    if first_stage.state == FirstStageState.TAIL_READY:
        age = float(seconds_since_current_min or 0.0)
        if age < float(required_tail_hold_s):
            return AuthorityDecision(AuthorityAction.CONTINUE, "tail_ready_but_hold_not_complete")
        if str(profile).upper() == "AGM" and int(agm_stage_idx) < int(agm_stage_count) - 1:
            return AuthorityDecision(
                AuthorityAction.ADVANCE_AGM_STEP,
                "agm_tail_hold_complete_advance_voltage_step",
            )
        if intent in RECOVERY_INTENTS:
            return AuthorityDecision(
                AuthorityAction.ENTER_MIX,
                "main_tail_hold_complete_recovery_hv_authorized",
            )
        return AuthorityDecision(
            AuthorityAction.COMPLETE_TO_SAFE_WAIT,
            "main_tail_hold_complete_normal_charge",
        )

    return AuthorityDecision(AuthorityAction.CONTINUE, "main_bulk_or_taper_continues")


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
        return AuthorityDecision(AuthorityAction.STOP_AND_DIAGNOSE, f"policy_{policy_decision.value}")
    if finish_hold_started_at is not None:
        held = max(0.0, float(now_s) - float(finish_hold_started_at))
        if held >= float(finish_hold_s):
            return AuthorityDecision(
                AuthorityAction.COMPLETE_TO_SAFE_WAIT,
                "confirmed_delta_finish_hold_complete",
            )
        return AuthorityDecision(AuthorityAction.CONTINUE, "confirmed_delta_finish_hold_running")
    if policy_decision == RecoveryDecision.FINISH_STAGE:
        return AuthorityDecision(
            AuthorityAction.START_FINISH_HOLD,
            "mode_specific_end_of_charge_evidence_confirmed",
        )
    if float(mix_elapsed_s) >= float(mix_limit_s):
        return AuthorityDecision(
            AuthorityAction.COMPLETE_TO_SAFE_WAIT,
            "mix_profile_observation_window_exhausted",
        )
    return AuthorityDecision(AuthorityAction.CONTINUE, "mix_observation_continues")
