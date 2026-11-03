"""Native recipe SAFE_WAIT preserves production continuation validation."""
import unittest

from runtime.charge.programs.native_recipe_catalog import native_recipes
from runtime.charge.programs.native_recipe_policy import native_policy
from runtime.charge.strategy.recovery_safe_wait import (
    RecoverySafeWaitContinuation, RecoverySafeWaitAction,
    decide_recovery_safe_wait,
)
from runtime.charge.strategy.final_safe_wait import (
    FinalSafeWaitContinuation, FinalSafeWaitAction, decide_final_safe_wait,
)


class NativeSafeWaitParityTests(unittest.TestCase):
    def test_both_safe_wait_paths_preserve_off_threshold_timeout_for_all_variants(self):
        recovery = RecoverySafeWaitContinuation(
            source_stage="DESULFATION", next_stage="MAIN",
            target_voltage_v=14.7, target_current_a=2.0,
            started_at=100., session_id="session",
            recovery_attempt=1, agm_stage_idx=0, session_generation=90.,
        )
        final = FinalSafeWaitContinuation(
            source_stage="MIX", next_stage="DONE",
            target_voltage_v=13.8, target_current_a=1.0,
            started_at=100., session_id="session",
            completion_reason="complete", session_generation=90.,
        )
        for entry in native_recipes():
            policy = native_policy(entry.recipe_id)
            for now, voltage, output_off in (
                (101., 14.8, False), (101., 14.8, True),
                (101., 14.0, True), (100000., 15.0, True),
            ):
                with self.subTest(entry=entry.recipe_id, now=now,
                                  voltage=voltage, off=output_off):
                    self.assertEqual(
                        policy.recovery_safe_wait_decision(
                            recovery, session_id="session", session_generation=90.,
                            expected_source_stage="DESULFATION",
                            expected_next_stage="MAIN", now_s=now,
                            voltage_v=voltage, output_is_off=output_off),
                        decide_recovery_safe_wait(
                            recovery, now_s=now, voltage_v=voltage,
                            output_is_off=output_off),
                    )
                    self.assertEqual(
                        policy.final_safe_wait_decision(
                            final, session_id="session", session_generation=90.,
                            expected_next_stage="DONE",
                            allowed_source_stages={"MAIN", "MIX"},
                            now_s=now, voltage_v=voltage,
                            output_is_off=output_off),
                        decide_final_safe_wait(
                            final, now_s=now, voltage_v=voltage,
                            output_is_off=output_off),
                    )

    def test_invalid_session_generation_is_rejected_without_resume(self):
        recovery = RecoverySafeWaitContinuation(
            source_stage="DESULFATION", next_stage="MAIN",
            target_voltage_v=14.7, target_current_a=2.0,
            started_at=100., session_id="original",
            recovery_attempt=1, agm_stage_idx=0, session_generation=90.,
        )
        final = FinalSafeWaitContinuation(
            source_stage="MIX", next_stage="DONE",
            target_voltage_v=13.8, target_current_a=1.0,
            started_at=100., session_id="original",
            completion_reason="complete", session_generation=90.,
        )
        for entry in native_recipes():
            policy = native_policy(entry.recipe_id)
            rec = policy.recovery_safe_wait_decision(
                recovery, session_id="different", session_generation=90.,
                expected_source_stage="DESULFATION", expected_next_stage="MAIN",
                now_s=100000., voltage_v=0., output_is_off=True)
            fin = policy.final_safe_wait_decision(
                final, session_id="original", session_generation=91.,
                expected_next_stage="DONE", allowed_source_stages={"MIX"},
                now_s=100000., voltage_v=0., output_is_off=True)
            self.assertEqual(rec.action, RecoverySafeWaitAction.REJECT)
            self.assertEqual(fin.action, FinalSafeWaitAction.REJECT)
