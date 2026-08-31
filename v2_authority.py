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


# NORMAL preserves the accepted V1 automatic charge chain: evidence-driven recovery
# and final Mix are part of a normal automatic charge. RECOVERY/CONDITIONING describe
# operator purpose/context and may later select additional policy, but they are not a
# prerequisite for the standard V1-compatible HV stages. DIAGNOSTIC is the explicit
# no-automatic-HV intent.
AUTOMATIC_HV_INTENTS = frozenset(
    {ChargeIntent.NORMAL, ChargeIntent.RECOVERY, ChargeIntent.CONDITIONING}
)
RECOVERY_INTENTS = AUTOMATIC_HV_INTENTS  # compatibility alias for older imports
AGM_TIMEOUT_TAIL_CURRENT_A = 0.20


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
    main_elapsed_s: Optional[float] = None,
    main_limit_s: Optional[float] = None,
    current_a: Optional[float] = None,
    is_cv: bool = False,
) -> AuthorityDecision:
    """Choose the authoritative Main transition.

    Important contracts:
    * NORMAL is V1-compatible full automatic charging, including bounded recovery/Mix.
    * DIAGNOSTIC never creates a new automatic HV stage.
    * Ca/EFB recovery attempts are a session-wide budget.
    * AGM is deliberately asymmetric: exhausted recovery attempts do not force Mix.
    * The 72 h Main limit is a strategy fallback, not a generic hard-safety shutdown.
    """
    _ = high_plateau_c_rate

    if _unsafe_policy_decision(policy_decision):
        return AuthorityDecision(
            AuthorityAction.STOP_AND_DIAGNOSE,
            f"policy_{policy_decision.value}",
        )

    profile_upper = str(profile).strip().upper()
    hv_allowed = intent in AUTOMATIC_HV_INTENTS

    # V1-compatible Main time fallback must work even when the trajectory never forms
    # a fixed plateau/tail evidence state (for example, current declines very slowly).
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
            if bool(is_cv) and current <= AGM_TIMEOUT_TAIL_CURRENT_A:
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
            # AGM dry-mat conservatism: four failed service attempts do not justify
            # forcing another HV transition. Stay in Main and require the normal
            # low-current tail (or the conservative 72 h fallback above).
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
        # A fallback maximum is the end of automatic HV authority, not evidence of
        # successful Mix completion.  Keep successful Delta/hold completion on the
        # SAFE_WAIT path, but time exhaustion must terminate and require diagnosis.
        return AuthorityDecision(
            AuthorityAction.STOP_AND_DIAGNOSE,
            "MIX_TIMEOUT",
        )
    return AuthorityDecision(AuthorityAction.CONTINUE, "mix_observation_continues")
