"""Static preflight for experimental recipes; not a physical START authorization."""
from __future__ import annotations

from dataclasses import dataclass
from .recipe_schema import Recipe


@dataclass(frozen=True)
class Preflight:
    admissible_structure: bool
    problems: tuple[str, ...]
    warnings: tuple[str, ...]


def inspect_recipe(recipe: Recipe) -> Preflight:
    """Check control-flow invariants before asking the existing session owner."""
    errors: list[str] = []
    warnings: list[str] = []
    if not recipe.steps:
        errors.append("recipe has no steps")
        return Preflight(False, tuple(errors), tuple(warnings))
    # WAIT must never unintentionally inherit an energized output.
    for index, step in enumerate(recipe.steps):
        action = step["action"]
        condition = next(iter(step["until"]))
        if action == "wait" and (index == 0 or recipe.steps[index - 1]["action"] != "off"):
            errors.append(f"step {index+1}: WAIT must immediately follow OFF")
        if action == "off" and index > 0 and recipe.steps[index - 1]["action"] == "off":
            warnings.append(f"step {index+1}: repeated OFF")
        if condition != "after_seconds":
            warnings.append(f"step {index+1}: sensor condition has no intrinsic timeout")
    if recipe.steps[0]["action"] == "wait":
        errors.append("first step may not be WAIT")
    return Preflight(not errors, tuple(errors), tuple(warnings))
