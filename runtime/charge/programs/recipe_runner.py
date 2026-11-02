"""Pure command-acknowledged orchestration; no physical actuator access."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .recipe_dispatch import (
    ActionReceipt, PendingAction, acknowledge_action, propose_action,
)
from .recipe_engine import StepState, evaluate_step
from .recipe_schema import Recipe


@dataclass(frozen=True)
class RunnerState:
    step: StepState | None = None
    pending: PendingAction | None = None
    completed: bool = False
    terminal_pending: bool = False


@dataclass(frozen=True)
class RunnerResult:
    state: RunnerState
    command: PendingAction | None
    blocked: bool


def tick(recipe: Recipe, runner: RunnerState, *, now_s: float,
         measurements: Mapping[str, float]) -> RunnerResult:
    """Advance only when no unacknowledged physical proposal exists."""
    if runner.completed:
        return RunnerResult(runner, None, False)
    if runner.pending is not None:
        return RunnerResult(runner, runner.pending, True)
    decision = evaluate_step(recipe, runner.step, now_s=now_s,
                             measurements=measurements)
    proposal = propose_action(recipe, decision)
    next_state = RunnerState(decision.state, proposal,
                             decision.completed and proposal is None,
                             decision.completed and proposal is not None)
    return RunnerResult(next_state, proposal, proposal is not None)


def confirm(runner: RunnerState, receipt: ActionReceipt, *, confirmed_at_s: float) -> RunnerState:
    """A failed/unverified receipt never clears the pending command."""
    if runner.pending is None:
        raise ValueError("no pending action")
    if not acknowledge_action(runner.pending, receipt):
        return runner
    from .recipe_engine import _finite
    confirmed_at_s = _finite(confirmed_at_s, "confirmation time")
    if runner.step is None or confirmed_at_s < runner.step.entered_at_s:
        raise ValueError("invalid confirmation time")
    step = StepState(runner.step.recipe_digest, runner.step.step_index,
                     confirmed_at_s)
    return RunnerState(step, None, runner.terminal_pending, False)
