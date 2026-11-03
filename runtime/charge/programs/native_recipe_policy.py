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
