"""Opt-in lifecycle for user recipes, isolated from legacy charge modes.

No registration in production loop, no physical START, no automatic resume.
A caller must own charge-session admission and provide its existing ExecutionPort.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Callable
from pathlib import Path

from application.recipe_execution_adapter import (
    RecipeExecutionIdentity, execute_recipe_action,
)
from runtime.charge.programs.recipe_dispatch import ActionReceipt
from runtime.charge.programs.recipe_runner import RunnerState, confirm, tick
from runtime.charge.programs.recipe_schema import Recipe
from runtime.charge.programs.recipe_preflight import inspect_recipe
from runtime.charge.programs.recipe_runner_store import save_runner, load_runner
from runtime.charge.programs.recipe_journal import append_event
from runtime.charge.programs.recipe_measurements import record_measurement
from application.execution_intent.models import SafetyContext


@dataclass(frozen=True)
class RecipeSession:
    recipe: Recipe
    identity: RecipeExecutionIdentity
    state: RunnerState = RunnerState()
    restored_inactive: bool = False


async def advance_recipe_session(
    session: RecipeSession, *, port: Any, now_s: float,
    measurements: Mapping[str, float], safety_context: SafetyContext,
    restart_limits: tuple[float, float, float] | None = None,
    persist_state: Callable[[RunnerState], None] | None = None,
) -> tuple[RecipeSession, ActionReceipt | None]:
    """Advance one step through canonical port; never perform START."""
    if session.restored_inactive:
        raise RuntimeError("restored session must not resume hardware automatically")
    if not session.identity.session_id or not session.identity.trace_id:
        raise PermissionError("missing existing session identity")
    report = inspect_recipe(session.recipe)
    if not report.admissible_structure:
        raise ValueError("recipe preflight failed: " + "; ".join(report.problems))
    result = tick(session.recipe, session.state, now_s=now_s,
                  measurements=measurements)
    if result.command is None:
        return RecipeSession(session.recipe, session.identity, result.state,
                             session.restored_inactive), None
    # Never blindly resend a command whose physical execution is uncertain.
    # This includes restoring a previously pending step after interruption.
    if session.state.pending is not None:
        raise RuntimeError("pending hardware action needs owner reconciliation")
    # Write-ahead pending state must survive process loss before physical I/O.
    if persist_state is None:
        raise RuntimeError("durable write-ahead state required for recipe hardware commands")
    persist_state(result.state)
    receipt = await execute_recipe_action(
        port=port, pending=result.command, identity=session.identity,
        safety_context=safety_context, restart_limits=restart_limits,
    )
    next_state = confirm(result.state, receipt, confirmed_at_s=now_s)
    persist_state(next_state)
    return RecipeSession(session.recipe, session.identity, next_state,
                         session.restored_inactive), receipt


def restore_recipe_session(*, recipe: Recipe,
                           identity: RecipeExecutionIdentity,
                           state: RunnerState) -> RecipeSession:
    """Restore only as inactive; explicit new owner admission is required."""
    if state.step is not None and state.step.recipe_digest != recipe.digest:
        raise ValueError("saved recipe mismatch")
    return RecipeSession(recipe, identity, state, True)


async def advance_durable_recipe_session(
    session: RecipeSession, *, port: Any, now_s: float,
    measurements: Mapping[str, float], safety_context: SafetyContext,
    restart_limits: tuple[float, float, float] | None = None,
    state_path: str | Path, journal_path: str | Path | None = None,
    measurement_path: str | Path | None = None,
) -> tuple[RecipeSession, ActionReceipt | None]:
    """Use the concrete fsynced runner store, not an unverified callback."""
    path = Path(state_path)
    if path.exists():
        saved = load_runner(path, session.recipe)
        if saved != session.state:
            raise RuntimeError("runner state differs from durable record")
    elif session.state != RunnerState():
        raise RuntimeError("progress exists without durable record")
    if measurement_path is not None:
        record_measurement(
            measurement_path, recipe=session.recipe,
            session_id=session.identity.session_id,
            timestamp_s=now_s, values=measurements,
        )
    def persist(state: RunnerState) -> None:
        save_runner(path, session.recipe, state)
        if journal_path is not None and state.pending is not None:
            append_event(journal_path, session_id=session.identity.session_id,
                         recipe_id=session.recipe.recipe_id, version=session.recipe.version,
                         digest=session.recipe.digest, event="PENDING",
                         action_id=state.pending.action_id)
    try:
        updated, receipt = await advance_recipe_session(
            session, port=port, now_s=now_s, measurements=measurements,
            safety_context=safety_context, restart_limits=restart_limits,
            persist_state=persist,
        )
    except Exception as exc:
        if journal_path is not None and path.exists():
            saved = load_runner(path, session.recipe)
            if saved.pending is not None:
                append_event(journal_path, session_id=session.identity.session_id,
                             recipe_id=session.recipe.recipe_id, version=session.recipe.version,
                             digest=session.recipe.digest, event="INTERRUPTED",
                             action_id=saved.pending.action_id, detail=type(exc).__name__)
        raise
    if journal_path is not None and receipt is not None:
        append_event(journal_path, session_id=session.identity.session_id,
                     recipe_id=session.recipe.recipe_id, version=session.recipe.version,
                     digest=session.recipe.digest,
                     event="VERIFIED" if receipt.verified else "UNVERIFIED",
                     action_id=receipt.action_id)
    return updated, receipt


def restore_durable_recipe_session(*, recipe: Recipe,
                                   identity: RecipeExecutionIdentity,
                                   state_path: str | Path) -> RecipeSession:
    """Restore as inactive; any pending action remains unresolved."""
    state = load_runner(state_path, recipe)
    return restore_recipe_session(recipe=recipe, identity=identity, state=state)
