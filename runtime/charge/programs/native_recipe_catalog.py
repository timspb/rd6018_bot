"""Read-only recipe descriptions of accepted production charge programs.

These entries describe *existing* owners, not approximations made of SET/OFF
steps. They cannot be executed by the user-recipe runner or written to its
library until policy/state equivalence exists. No hardware interfaces here.
"""
from __future__ import annotations

from dataclasses import dataclass

# The production entrypoint offers 3 chemistries x 4 intents.  Those are
# recipe variants, not twelve independent hardware-owning loops.
PROFILES = ("Ca/Ca", "EFB", "AGM")
INTENTS = ("normal", "recovery", "conditioning", "diagnostic")


@dataclass(frozen=True)
class NativeRecipeDescription:
    recipe_id: str
    profile: str
    intent: str
    stages: tuple[str, ...]
    owner_modules: tuple[str, ...]
    execution_kind: str = "native_authority"
    editable: bool = False
    executable_by_user_recipe_runner: bool = False


# These are actual runtime owners in application/charge_stage_tick.py.
STAGE_OWNERS = (
    ("PREP", "runtime.charge.runtime.residual_scaffold"),
    ("MAIN", "runtime.charge.runtime.main_scaffold"),
    ("DESULFATION", "runtime.charge.runtime.recovery_scaffold"),
    ("RECOVERY_SAFE_WAIT", "runtime.charge.runtime.recovery_scaffold"),
    ("MIX", "runtime.charge.runtime.mix_scaffold"),
    ("FINAL_SAFE_WAIT", "runtime.charge.runtime.mix_scaffold"),
    ("COOLING", "runtime.charge.runtime.residual_scaffold"),
    ("DONE", "runtime.charge.runtime.residual_scaffold"),
)


def native_recipes() -> tuple[NativeRecipeDescription, ...]:
    """Inventory, not a static simulation of safety-dependent branching."""
    result = []
    for profile in PROFILES:
        for intent in INTENTS:
            # DIAGNOSTIC forbids starting new automatic high-voltage stages;
            # other paths are conditional, not guaranteed sequential stages.
            stages = tuple(name for name, _ in STAGE_OWNERS
                           if intent != "diagnostic" or name not in {
                               "DESULFATION", "RECOVERY_SAFE_WAIT", "MIX",
                               "FINAL_SAFE_WAIT"})
            owners = tuple(dict.fromkeys(module for name, module in STAGE_OWNERS
                                          if name in stages))
            result.append(NativeRecipeDescription(
                recipe_id=f"native_{profile.lower().replace('/', '_')}_{intent}",
                profile=profile, intent=intent, stages=stages,
                owner_modules=owners,
            ))
    return tuple(result)


def get_native_recipe(recipe_id: str) -> NativeRecipeDescription:
    for recipe in native_recipes():
        if recipe.recipe_id == recipe_id:
            return recipe
    raise KeyError(recipe_id)
