import unittest

from first_stage_evidence import FirstStageAssessment, FirstStageState
from pb_domain import ChargeIntent
from recovery_policy import RecoveryDecision
from v2_authority import AuthorityAction, decide_main_transition, decide_mix_transition


def assessment(state, *, c_rate=0.004, threshold=0.28):
    return FirstStageAssessment(
        state=state,
        current_c_rate=c_rate,
        tail_threshold_a=threshold,
        tail_threshold_c=0.004,
        near_target=True,
        reason=state.value,
    )


def main_decision(**overrides):
    params = dict(
        profile="EFB",
        intent=ChargeIntent.NORMAL,
        first_stage=assessment(FirstStageState.BULK_OR_TAPER),
        policy_decision=RecoveryDecision.CONTINUE,
        seconds_since_current_min=None,
        required_tail_hold_s=3 * 3600,
        desulf_attempts=0,
        max_desulf_attempts=3,
    )
    params.update(overrides)
    return decide_main_transition(**params)


class V2MainAuthorityTests(unittest.TestCase):
    def test_normal_is_v1_compatible_and_plateau_can_enter_recovery(self):
        result = main_decision(first_stage=assessment(FirstStageState.STUCK_PLATEAU))
        self.assertEqual(result.action, AuthorityAction.ENTER_DESULFATION)

    def test_diagnostic_plateau_never_creates_hv(self):
        result = main_decision(
            intent=ChargeIntent.DIAGNOSTIC,
            first_stage=assessment(FirstStageState.STUCK_PLATEAU),
        )
        self.assertEqual(result.action, AuthorityAction.STOP_AND_DIAGNOSE)

    def test_recovery_confirmed_plateau_is_not_blocked_by_c_rate_alone(self):
        result = main_decision(
            intent=ChargeIntent.RECOVERY,
            first_stage=assessment(FirstStageState.STUCK_PLATEAU, c_rate=0.018),
            desulf_attempts=1,
        )
        self.assertEqual(result.action, AuthorityAction.ENTER_DESULFATION)

    def test_ca_efb_recovery_budget_is_session_wide_then_mix(self):
        for attempts in (0, 1, 2):
            result = main_decision(
                profile="Ca/Ca",
                first_stage=assessment(FirstStageState.STUCK_PLATEAU),
                desulf_attempts=attempts,
            )
            self.assertEqual(result.action, AuthorityAction.ENTER_DESULFATION)
        exhausted = main_decision(
            profile="Ca/Ca",
            first_stage=assessment(FirstStageState.STUCK_PLATEAU),
            desulf_attempts=3,
        )
        self.assertEqual(exhausted.action, AuthorityAction.ENTER_MIX)

    def test_agm_budget_is_four_session_wide_and_exhaustion_waits_for_tail(self):
        for attempts in (0, 1, 2, 3):
            result = main_decision(
                profile="AGM",
                first_stage=assessment(FirstStageState.STUCK_PLATEAU),
                required_tail_hold_s=2 * 3600,
                desulf_attempts=attempts,
                max_desulf_attempts=4,
            )
            self.assertEqual(result.action, AuthorityAction.ENTER_DESULFATION)
        exhausted = main_decision(
            profile="AGM",
            first_stage=assessment(FirstStageState.STUCK_PLATEAU),
            required_tail_hold_s=2 * 3600,
            desulf_attempts=4,
            max_desulf_attempts=4,
        )
        self.assertEqual(exhausted.action, AuthorityAction.CONTINUE)
        self.assertIn("wait_for_tail", exhausted.reason)

    def test_tail_hold_advances_agm_steps_before_final_mix(self):
        result = main_decision(
            profile="AGM",
            first_stage=assessment(FirstStageState.TAIL_READY),
            seconds_since_current_min=2 * 3600,
            required_tail_hold_s=2 * 3600,
            agm_stage_idx=1,
            agm_stage_count=4,
            max_desulf_attempts=4,
        )
        self.assertEqual(result.action, AuthorityAction.ADVANCE_AGM_STEP)

    def test_normal_final_tail_enters_mix(self):
        result = main_decision(
            profile="AGM",
            first_stage=assessment(FirstStageState.TAIL_READY),
            seconds_since_current_min=2 * 3600,
            required_tail_hold_s=2 * 3600,
            agm_stage_idx=3,
            agm_stage_count=4,
            max_desulf_attempts=4,
        )
        self.assertEqual(result.action, AuthorityAction.ENTER_MIX)

    def test_diagnostic_final_tail_finishes_without_mix(self):
        result = main_decision(
            profile="AGM",
            intent=ChargeIntent.DIAGNOSTIC,
            first_stage=assessment(FirstStageState.TAIL_READY),
            seconds_since_current_min=2 * 3600,
            required_tail_hold_s=2 * 3600,
            agm_stage_idx=3,
            agm_stage_count=4,
            max_desulf_attempts=4,
        )
        self.assertEqual(result.action, AuthorityAction.COMPLETE_TO_SAFE_WAIT)

    def test_ca_efb_72h_fallback_enters_mix_even_without_plateau(self):
        result = main_decision(
            first_stage=None,
            main_elapsed_s=72 * 3600,
            main_limit_s=72 * 3600,
            current_a=0.8,
            is_cv=True,
        )
        self.assertEqual(result.action, AuthorityAction.ENTER_MIX)
        self.assertIn("v1_compatible", result.reason)

    def test_diagnostic_72h_fallback_never_enters_hv(self):
        result = main_decision(
            intent=ChargeIntent.DIAGNOSTIC,
            first_stage=None,
            main_elapsed_s=72 * 3600,
            main_limit_s=72 * 3600,
            current_a=0.2,
            is_cv=True,
        )
        self.assertEqual(result.action, AuthorityAction.STOP_AND_DIAGNOSE)

    def test_agm_72h_mix_requires_cv_and_current_not_above_0_2a(self):
        ok = main_decision(
            profile="AGM",
            first_stage=None,
            required_tail_hold_s=2 * 3600,
            max_desulf_attempts=4,
            main_elapsed_s=72 * 3600,
            main_limit_s=72 * 3600,
            current_a=0.2,
            is_cv=True,
        )
        self.assertEqual(ok.action, AuthorityAction.ENTER_MIX)
        high = main_decision(
            profile="AGM",
            first_stage=None,
            required_tail_hold_s=2 * 3600,
            max_desulf_attempts=4,
            main_elapsed_s=72 * 3600,
            main_limit_s=72 * 3600,
            current_a=0.21,
            is_cv=True,
        )
        self.assertEqual(high.action, AuthorityAction.STOP_AND_DIAGNOSE)
        not_cv = main_decision(
            profile="AGM",
            first_stage=None,
            required_tail_hold_s=2 * 3600,
            max_desulf_attempts=4,
            main_elapsed_s=72 * 3600,
            main_limit_s=72 * 3600,
            current_a=0.1,
            is_cv=False,
        )
        self.assertEqual(not_cv.action, AuthorityAction.STOP_AND_DIAGNOSE)

    def test_thermal_policy_always_beats_hv(self):
        result = main_decision(
            first_stage=assessment(FirstStageState.TAIL_READY),
            policy_decision=RecoveryDecision.PAUSE_THERMAL,
            seconds_since_current_min=10 * 3600,
            main_elapsed_s=80 * 3600,
            main_limit_s=72 * 3600,
        )
        self.assertEqual(result.action, AuthorityAction.STOP_AND_DIAGNOSE)


class V2MixAuthorityTests(unittest.TestCase):
    def test_finish_evidence_starts_hold_not_immediate_completion(self):
        result = decide_mix_transition(
            policy_decision=RecoveryDecision.FINISH_STAGE,
            mix_elapsed_s=3 * 3600,
            mix_limit_s=10 * 3600,
            finish_hold_started_at=None,
            now_s=10000,
            finish_hold_s=2 * 3600,
        )
        self.assertEqual(result.action, AuthorityAction.START_FINISH_HOLD)

    def test_active_finish_hold_owns_completion_past_profile_deadline(self):
        result = decide_mix_transition(
            policy_decision=RecoveryDecision.CONTINUE,
            mix_elapsed_s=21 * 3600,
            mix_limit_s=20 * 3600,
            finish_hold_started_at=1000,
            now_s=1000 + 3600,
            finish_hold_s=2 * 3600,
        )
        self.assertEqual(result.action, AuthorityAction.CONTINUE)

    def test_hold_completes_after_two_hours(self):
        result = decide_mix_transition(
            policy_decision=RecoveryDecision.CONTINUE,
            mix_elapsed_s=21 * 3600,
            mix_limit_s=20 * 3600,
            finish_hold_started_at=1000,
            now_s=1000 + 2 * 3600,
            finish_hold_s=2 * 3600,
        )
        self.assertEqual(result.action, AuthorityAction.COMPLETE_TO_SAFE_WAIT)

    def test_profile_window_is_fault_boundary_without_finish_hold(self):
        result = decide_mix_transition(
            policy_decision=RecoveryDecision.CONTINUE,
            mix_elapsed_s=20 * 3600,
            mix_limit_s=20 * 3600,
            finish_hold_started_at=None,
            now_s=1000,
            finish_hold_s=2 * 3600,
        )
        self.assertEqual(result.action, AuthorityAction.STOP_AND_DIAGNOSE)
        self.assertEqual(result.reason, "MIX_TIMEOUT")


if __name__ == "__main__":
    unittest.main()
