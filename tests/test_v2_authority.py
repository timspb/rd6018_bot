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


class V2MainAuthorityTests(unittest.TestCase):
    def test_normal_intent_never_escalates_persistent_plateau_to_hv(self):
        result = decide_main_transition(
            profile="EFB",
            intent=ChargeIntent.NORMAL,
            first_stage=assessment(FirstStageState.STUCK_PLATEAU),
            policy_decision=RecoveryDecision.CONTINUE,
            seconds_since_current_min=None,
            required_tail_hold_s=3 * 3600,
            desulf_attempts=0,
            max_desulf_attempts=3,
        )
        self.assertEqual(result.action, AuthorityAction.STOP_AND_DIAGNOSE)

    def test_recovery_moderate_plateau_can_enter_desulfation(self):
        result = decide_main_transition(
            profile="EFB",
            intent=ChargeIntent.RECOVERY,
            first_stage=assessment(FirstStageState.STUCK_PLATEAU, c_rate=0.006),
            policy_decision=RecoveryDecision.CONTINUE,
            seconds_since_current_min=None,
            required_tail_hold_s=3 * 3600,
            desulf_attempts=1,
            max_desulf_attempts=3,
        )
        self.assertEqual(result.action, AuthorityAction.ENTER_DESULFATION)

    def test_plateau_above_one_percent_c_is_not_auto_escalated(self):
        result = decide_main_transition(
            profile="EFB",
            intent=ChargeIntent.RECOVERY,
            first_stage=assessment(FirstStageState.STUCK_PLATEAU, c_rate=0.012),
            policy_decision=RecoveryDecision.CONTINUE,
            seconds_since_current_min=None,
            required_tail_hold_s=3 * 3600,
            desulf_attempts=0,
            max_desulf_attempts=3,
        )
        self.assertEqual(result.action, AuthorityAction.STOP_AND_DIAGNOSE)

    def test_tail_hold_advances_agm_steps_before_hv(self):
        result = decide_main_transition(
            profile="AGM",
            intent=ChargeIntent.RECOVERY,
            first_stage=assessment(FirstStageState.TAIL_READY, c_rate=0.0025),
            policy_decision=RecoveryDecision.CONTINUE,
            seconds_since_current_min=2 * 3600,
            required_tail_hold_s=2 * 3600,
            agm_stage_idx=1,
            agm_stage_count=4,
        )
        self.assertEqual(result.action, AuthorityAction.ADVANCE_AGM_STEP)

    def test_normal_final_tail_completes_without_hv(self):
        result = decide_main_transition(
            profile="AGM",
            intent=ChargeIntent.NORMAL,
            first_stage=assessment(FirstStageState.TAIL_READY, c_rate=0.0025),
            policy_decision=RecoveryDecision.CONTINUE,
            seconds_since_current_min=2 * 3600,
            required_tail_hold_s=2 * 3600,
            agm_stage_idx=3,
            agm_stage_count=4,
        )
        self.assertEqual(result.action, AuthorityAction.COMPLETE_TO_SAFE_WAIT)

    def test_recovery_final_tail_enters_mix(self):
        result = decide_main_transition(
            profile="AGM",
            intent=ChargeIntent.RECOVERY,
            first_stage=assessment(FirstStageState.TAIL_READY, c_rate=0.0025),
            policy_decision=RecoveryDecision.CONTINUE,
            seconds_since_current_min=2 * 3600,
            required_tail_hold_s=2 * 3600,
            agm_stage_idx=3,
            agm_stage_count=4,
        )
        self.assertEqual(result.action, AuthorityAction.ENTER_MIX)

    def test_thermal_policy_always_stops_before_hv(self):
        result = decide_main_transition(
            profile="Ca/Ca",
            intent=ChargeIntent.RECOVERY,
            first_stage=assessment(FirstStageState.TAIL_READY),
            policy_decision=RecoveryDecision.PAUSE_THERMAL,
            seconds_since_current_min=10 * 3600,
            required_tail_hold_s=3 * 3600,
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
        self.assertIn("hold_running", result.reason)

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

    def test_profile_window_is_fallback_without_finish_hold(self):
        result = decide_mix_transition(
            policy_decision=RecoveryDecision.CONTINUE,
            mix_elapsed_s=20 * 3600,
            mix_limit_s=20 * 3600,
            finish_hold_started_at=None,
            now_s=1000,
            finish_hold_s=2 * 3600,
        )
        self.assertEqual(result.action, AuthorityAction.COMPLETE_TO_SAFE_WAIT)

    def test_thermal_evidence_beats_finish_hold(self):
        result = decide_mix_transition(
            policy_decision=RecoveryDecision.PAUSE_THERMAL,
            mix_elapsed_s=12 * 3600,
            mix_limit_s=20 * 3600,
            finish_hold_started_at=1000,
            now_s=1000 + 2 * 3600,
            finish_hold_s=2 * 3600,
        )
        self.assertEqual(result.action, AuthorityAction.STOP_AND_DIAGNOSE)


if __name__ == "__main__":
    unittest.main()
