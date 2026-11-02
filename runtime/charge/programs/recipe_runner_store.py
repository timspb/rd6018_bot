"""Durable write-ahead store for complete recipe runner state, with no auto-resume."""
from __future__ import annotations

from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import tempfile

from .recipe_engine import StepState
from .recipe_dispatch import PendingAction, propose_action
from .recipe_runner import RunnerState
from .recipe_schema import Recipe


def _validate(recipe: Recipe, state: RunnerState) -> None:
    if state.step is None:
        if state.pending is not None or state.completed or state.terminal_pending:
            raise ValueError("uninitialized runner cannot have progress")
        return
    step = state.step
    if step.recipe_digest != recipe.digest or type(step.step_index) is not int:
        raise ValueError("runner recipe mismatch")
    if not 0 <= step.step_index <= len(recipe.steps):
        raise ValueError("invalid runner index")
    if not math.isfinite(step.entered_at_s) or step.entered_at_s < 0:
        raise ValueError("invalid runner timestamp")
    if state.completed and (state.pending is not None or step.step_index != len(recipe.steps)):
        raise ValueError("invalid completed state")
    if state.terminal_pending and (state.pending is None or step.step_index != len(recipe.steps)):
        raise ValueError("invalid terminal pending state")
    if state.pending is not None:
        pending = state.pending
        if pending.recipe_digest != recipe.digest or pending.step_index != step.step_index:
            raise ValueError("pending recipe mismatch")
        from .recipe_engine import StepDecision
        expected = propose_action(recipe, StepDecision(step, False, False,
            pending.operation, pending.parameters))
        if expected is None or expected.action_id != pending.action_id:
            raise ValueError("pending action identity mismatch")


def save_runner(path: str | Path, recipe: Recipe, state: RunnerState) -> None:
    _validate(recipe, state)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {"schema": 1, "recipe_id": recipe.recipe_id, "version": recipe.version,
            "digest": recipe.digest, "state": asdict(state)}
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent,
                                         prefix=".runner-", delete=False) as f:
            temp = f.name
            json.dump(data, f, sort_keys=True, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, target)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


def load_runner(path: str | Path, recipe: Recipe) -> RunnerState:
    with Path(path).open(encoding="utf-8") as f:
        data = json.load(f)
    if data.get("schema") != 1 or data.get("recipe_id") != recipe.recipe_id or data.get("version") != recipe.version or data.get("digest") != recipe.digest:
        raise ValueError("runner revision mismatch")
    raw = data["state"]
    if set(raw) != {"step", "pending", "completed", "terminal_pending"}:
        raise ValueError("invalid runner state schema")
    if type(raw["completed"]) is not bool or type(raw["terminal_pending"]) is not bool:
        raise ValueError("invalid runner flags")
    step = StepState(**raw["step"]) if raw["step"] is not None else None
    pending = PendingAction(**raw["pending"]) if raw["pending"] is not None else None
    state = RunnerState(step, pending, raw["completed"], raw["terminal_pending"])
    _validate(recipe, state)
    return state
