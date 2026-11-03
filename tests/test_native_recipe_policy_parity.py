"""The native recipe interface returns unchanged production decisions."""
import unittest

from recovery_policy import RecoveryDecision
from runtime.charge.evidence.first_stage import FirstStageAssessment, FirstStageState
from runtime.charge.programs.native_recipe_catalog import native_recipes
from runtime.charge.programs.native_recipe_policy import native_policy
from runtime.charge.strategy.main_authority import decide_main_transition
from runtime.charge.strategy.mix import decide_mix_transition


class NativeRecipePolicyParityTests(unittest.TestCase):
    def test_main_bulk_tail_plateau_and_unsafe_decisions_all_variants(self):
        for entry in native_recipes():
            policy = native_policy(entry.recipe_id)
            for state, recovery in (
                (None, RecoveryDecision.CONTINUE),
                (FirstStageState.BULK_OR_TAPER, RecoveryDecision.CONTINUE),
                (FirstStageState.TAIL_READY, RecoveryDecision.CONTINUE),
                (FirstStageState.STUCK_PLATEAU, RecoveryDecision.CONTINUE),
                (None, RecoveryDecision.PAUSE_THERMAL),
            ):
                assessment = None if state is None else FirstStageAssessment(
                    state=state, current_c_rate=0.02, tail_threshold_a=1.0,
                    tail_threshold_c=0.02, near_target=True, reason="test")
                kwargs = dict(
                    first_stage=assessment, policy_decision=recovery,
                    seconds_since_current_min=1200.0, required_tail_hold_s=600.0,
                    desulf_attempts=0, max_desulf_attempts=2,
                    main_elapsed_s=180.0, main_limit_s=3600.0,
                    current_a=0.5, is_cv=True,
                )
                with self.subTest(recipe=entry.recipe_id, state=state, recovery=recovery):
                    self.assertEqual(
                        policy.main_decision(**kwargs),
                        decide_main_transition(profile=entry.profile,
                                               intent=entry.intent, **kwargs),
                    )

    def test_mix_observing_hold_completed_timeout_and_unsafe_all_variants(self):
        for entry in native_recipes():
            policy = native_policy(entry.recipe_id)
            for recovery, elapsed, started, now in (
                (RecoveryDecision.CONTINUE, 10., None, 100.),
                (RecoveryDecision.FINISH_STAGE, 10., None, 100.),
                (RecoveryDecision.CONTINUE, 10., 20., 100.),
                (RecoveryDecision.CONTINUE, 10., 20., 200.),
                (RecoveryDecision.CONTINUE, 500., None, 100.),
                (RecoveryDecision.HOLD_OUTPUT_OFF, 10., None, 100.),
            ):
                kwargs = dict(policy_decision=recovery, active_elapsed_s=elapsed,
                              finish_hold_started_at=started, now_s=now,
                              authority_limit_s=300., finish_hold_s=120.)
                with self.subTest(recipe=entry.recipe_id, recovery=recovery,
                                  elapsed=elapsed, started=started, now=now):
                    self.assertEqual(
                        policy.mix_decision(**kwargs),
                        decide_mix_transition(profile=entry.profile, **kwargs),
                    )

    def test_recipe_identity_cannot_be_replaced_by_caller(self):
        policy = native_policy("native_agm_normal")
        with self.assertRaises(ValueError):
            policy.main_decision(profile="Ca/Ca")
        with self.assertRaises(ValueError):
            policy.main_decision(intent="diagnostic")
        with self.assertRaises(ValueError):
            policy.mix_decision(profile="EFB")
