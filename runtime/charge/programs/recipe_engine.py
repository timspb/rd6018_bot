"""Pure recipe step evaluator; never invokes RD6018 or applies hardware actions."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from .recipe_schema import Recipe, CONDITIONS


@dataclass(frozen=True)
class StepState:
    recipe_digest: str
    step_index: int
    entered_at_s: float


@dataclass(frozen=True)
class StepDecision:
    state: StepState
    transitioned: bool
    completed: bool
    proposed_action: str | None
    parameters: dict[str, float]


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: numeric measurement required")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name}: finite measurement required")
    return out

def evaluate_step(recipe: Recipe, state: StepState | None, *,
                  now_s: float, measurements: Mapping[str, float]) -> StepDecision:
    """One transition per invocation, emitting only an unexecuted action proposal."""
    now = _finite(now_s, "clock")
    if state is None:
        state = StepState(recipe.digest, 0, now)
        initial = recipe.steps[0]
        return StepDecision(state, False, False, initial["action"],
                            dict(initial["params"]))
    if state.recipe_digest != recipe.digest:
        raise ValueError("recipe revision changed during execution")
    if not 0 <= state.step_index <= len(recipe.steps):
        raise ValueError("invalid step index")
    if now < state.entered_at_s:
        raise ValueError("clock moved backwards")
    if state.step_index == len(recipe.steps):
        return StepDecision(state, False, True, None, {})
    step = recipe.steps[state.step_index]
    condition, threshold = next(iter(step["until"].items()))
    if condition == "after_seconds":
        reached = now - state.entered_at_s >= threshold
    else:
        name, comparison = condition.rsplit("_", 1)
        if name not in measurements:
            raise ValueError(f"missing measurement: {name}")
        actual = _finite(measurements[name], name)
        reached = actual >= threshold if comparison == "gte" else actual <= threshold
    if not reached:
        return StepDecision(state, False, False, None, {})
    next_index = state.step_index + 1
    new_state = StepState(recipe.digest, next_index, now)
    if next_index == len(recipe.steps):
        return StepDecision(new_state, True, True, "off", {})
    nxt = recipe.steps[next_index]
    return StepDecision(new_state, True, False, nxt["action"], dict(nxt["params"]))
