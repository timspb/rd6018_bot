"""Resolve a user recipe for the existing transactional START owner.

Selection is read-only and deterministic for the requested immutable version.
It does not create a runner, persist session state, or authorize physical START.
"""
from __future__ import annotations

from typing import Any

def select_user_recipe_for_start(*, catalog: Any, recipe_id: str,
                                 version: int) -> Any:
    """Load and validate the selected immutable recipe before START.

    Profile START enables Output using the first SET transactionally, so a
    user recipe selected for that route must begin with SET. OFF/WAIT-first
    recipes remain available to their existing non-START workflows.
    """
    recipe = catalog.library.load(str(recipe_id), int(version))
    from runtime.charge.programs.recipe_preflight import inspect_recipe
    report = inspect_recipe(recipe)
    if not report.admissible_structure:
        raise ValueError("; ".join(report.problems))
    if recipe.steps[0]["action"] != "set":
        raise ValueError(
            "Для START первый шаг пользовательского рецепта должен быть SET. "
            "Черновик OFF не запускается и не включает Output."
        )
    return recipe


__all__ = ["select_user_recipe_for_start"]
