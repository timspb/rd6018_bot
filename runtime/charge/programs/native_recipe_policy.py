"""Executable *decision-only* native recipe surface using production policy.

No copied stage logic, hardware calls, target overrides or runtime cutover.
Normal profile/intent and existing MAIN/MIX policy owners remain authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .native_recipe_catalog import NativeRecipeDescription, get_native_recipe


@dataclass(frozen=True)
class NativeRecipePolicy:
    description: NativeRecipeDescription

    def main_decision(self, **evidence: Any):
        """Evaluate MAIN exactly as the existing production strategy."""
        from runtime.charge.strategy.main_authority import decide_main_transition
        if "profile" in evidence or "intent" in evidence:
            raise ValueError("native recipe profile/intent are immutable")
        return decide_main_transition(
            profile=self.description.profile,
            intent=self.description.intent,
            **evidence,
        )

    def desulfation_decision(self, *, active_elapsed_s: float):
        """Preserve the bounded recovery strategy's accepted time semantics."""
        from runtime.charge.strategy.desulfation import decide_desulfation
        return decide_desulfation(active_elapsed_s=active_elapsed_s)

    def desulfation_target(self, *, capacity_ah: float):
        """Return the existing recovery target; no actuator operation."""
        from runtime.charge.strategy.desulfation import select_desulfation_target
        return select_desulfation_target(capacity_ah=capacity_ah)

    def recovery_safe_wait_decision(self, continuation: Any, *,
                                    session_id: str | None,
                                    session_generation: float | None,
                                    expected_source_stage: str,
                                    expected_next_stage: str,
                                    now_s: float, voltage_v: float,
                                    output_is_off: bool):
        """Use the existing Recovery SAFE_WAIT validator and decision owner."""
        from runtime.charge.strategy.recovery_safe_wait import (
            RecoverySafeWaitAction, RecoverySafeWaitDecision,
            decide_recovery_safe_wait, validate_recovery_continuation,
        )
        if not validate_recovery_continuation(
            continuation, session_id=session_id,
            session_generation=session_generation,
            expected_source_stage=expected_source_stage,
            expected_next_stage=expected_next_stage,
        ):
            return RecoverySafeWaitDecision(RecoverySafeWaitAction.REJECT,
                                            "invalid_continuation", 0.0, 0.0)
        return decide_recovery_safe_wait(
            continuation, now_s=now_s, voltage_v=voltage_v,
            output_is_off=output_is_off,
        )

    def final_safe_wait_decision(self, continuation: Any, *,
                                 session_id: str | None,
                                 session_generation: float | None,
                                 expected_next_stage: str,
                                 allowed_source_stages: set[str],
                                 now_s: float, voltage_v: float,
                                 output_is_off: bool):
        """Use the existing Final SAFE_WAIT validator and decision owner."""
        from runtime.charge.strategy.final_safe_wait import (
            FinalSafeWaitAction, FinalSafeWaitDecision,
            decide_final_safe_wait, validate_final_continuation,
        )
        if not validate_final_continuation(
            continuation, session_id=session_id,
            session_generation=session_generation,
            expected_next_stage=expected_next_stage,
            allowed_source_stages=allowed_source_stages,
        ):
            return FinalSafeWaitDecision(FinalSafeWaitAction.REJECT,
                                         "invalid_continuation", 0.0, 0.0)
        return decide_final_safe_wait(
            continuation, now_s=now_s, voltage_v=voltage_v,
            output_is_off=output_is_off,
        )

    def mix_target(self, *, capacity_ah: float):
        """Return the existing chemistry-dependent MIX target.

        This does not authorize MIX admission. Production thermal compensation
        and the live recipe envelope still apply at the execution boundary.
        """
        from runtime.charge.strategy.mix import select_mix_target
        return select_mix_target(
            profile=self.description.profile, capacity_ah=capacity_ah,
        )

    def mix_decision(self, **evidence: Any):
        """Evaluate MIX by delegating to its existing production owner.

        This is a parity interface, not permission to enter high voltage.
        Stage admission and safety veto remain in the production runtime.
        """
        from runtime.charge.strategy.mix import decide_mix_transition
        if "profile" in evidence:
            raise ValueError("native recipe profile is immutable")
        return decide_mix_transition(profile=self.description.profile, **evidence)


def native_policy(recipe_id: str) -> NativeRecipePolicy:
    return NativeRecipePolicy(get_native_recipe(recipe_id))
