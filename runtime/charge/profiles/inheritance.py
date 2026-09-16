"""Safe, whitelisted factory-recipe inheritance."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .recipe import ValidatedChargeRecipe


class RecipeOverrideError(ValueError):
    pass


ALLOWED = {
    "mix.cc.delta_voltage", "mix.cv.delta_current",
    "mix.cc.hold_seconds", "mix.cv.hold_seconds",
}


def apply_recipe_override(base: ValidatedChargeRecipe, overrides: Mapping[str, Any]) -> ValidatedChargeRecipe:
    unknown = set(overrides) - ALLOWED
    if unknown:
        raise RecipeOverrideError(f"override fields are not allowed: {sorted(unknown)}")
    cc = base.recipe.mix.config.cc
    cv = base.recipe.mix.config.cv
    for key, value in overrides.items():
        if not isinstance(value, (int, float)) or value <= 0:
            raise RecipeOverrideError(f"override value must be positive: {key}")
        if key == "mix.cc.delta_voltage":
            cc = replace(cc, delta_voltage=float(value))
        elif key == "mix.cv.delta_current":
            cv = replace(cv, delta_current=float(value))
        elif key == "mix.cc.hold_seconds":
            cc = replace(cc, hold_seconds=float(value))
        elif key == "mix.cv.hold_seconds":
            cv = replace(cv, hold_seconds=float(value))
    mix = replace(base.recipe.mix.config, cc=cc, cv=cv)
    from ..strategy import MixPolicy
    recipe = replace(base.recipe, mix=MixPolicy(mix, authority=base.recipe.mix.authority))
    return replace(base, recipe=recipe, source="factory+override")
