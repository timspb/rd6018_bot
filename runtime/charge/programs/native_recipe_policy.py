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
