"""Opt-in lifecycle for user recipes, isolated from legacy charge modes.

No registration in production loop, no physical START, no automatic resume.
A caller must own charge-session admission and provide its existing ExecutionPort.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from application.recipe_execution_adapter import (
    RecipeExecutionIdentity, execute_recipe_action,
)
from runtime.charge.programs.recipe_dispatch import ActionReceipt
from runtime.charge.programs.recipe_runner import RunnerState, confirm, tick
from runtime.charge.programs.recipe_schema import Recipe


@dataclass(frozen=True)
class RecipeSession:
    recipe: Recipe
    identity: RecipeExecutionIdentity
    state: RunnerState = RunnerState()
    admission_epoch: str = ""


async def advance_recipe_session(
    session: RecipeSession, *, port: Any, now_s: float,
    measurements: Mapping[str, float], admitted_epoch: str,
) -> tuple[RecipeSession, ActionReceipt | None]:
    """Advance one step through canonical port; never perform START."""
    if not session.admission_epoch or session.admission_epoch != admitted_epoch:
        raise PermissionError("session admission epoch mismatch")
    result = tick(session.recipe, session.state, now_s=now_s,
                  measurements=measurements)
    if result.command is None:
        return RecipeSession(session.recipe, session.identity, result.state,
                             session.admission_epoch), None
    # Never blindly resend a command whose physical execution is uncertain.
    # This includes restoring a previously pending step after interruption.
    if session.state.pending is not None:
        raise RuntimeError("pending hardware action needs owner reconciliation")
    receipt = await execute_recipe_action(
        port=port, pending=result.command, identity=session.identity,
        admitted=True,
    )
    next_state = confirm(result.state, receipt, confirmed_at_s=now_s)
    return RecipeSession(session.recipe, session.identity, next_state,
                         session.admission_epoch), receipt


def restore_recipe_session(*, recipe: Recipe,
                           identity: RecipeExecutionIdentity,
                           state: RunnerState) -> RecipeSession:
    """Restore only as inactive; explicit new owner admission is required."""
    if state.step is not None and state.step.recipe_digest != recipe.digest:
        raise ValueError("saved recipe mismatch")
    return RecipeSession(recipe, identity, state, "")
