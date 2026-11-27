"""Advance a recipe within the already-owned production charging session.

This is a callable adapter, not a new loop, START path, or session owner.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from application.execution_intent.models import SafetyContext
from application.recipe_execution_adapter import RecipeExecutionIdentity
from runtime.charge.programs.recipe_preflight import inspect_recipe
from application.recipe_session_lifecycle import (
    RecipeSession, advance_durable_recipe_session,
)
from runtime.charge.programs.recipe_runner import tick


@dataclass
class ExistingRecipeBinding:
    session: RecipeSession
    port: Any
    safety_context: SafetyContext
    voltage_ceiling_v: float
    state_path: str | Path
    journal_path: str | Path | None = None
    measurement_path: str | Path | None = None


def prepare_existing_recipe_binding(*, catalog, recipe_id: str, version: int,
                                    port: Any, identity: RecipeExecutionIdentity,
                                    safety_context: SafetyContext, voltage_ceiling_v: float,
                                    state_path: str | Path,
                                    recipe: Any | None = None,
                                    journal_path: str | Path | None = None,
                                    measurement_path: str | Path | None = None) -> ExistingRecipeBinding:
    """Resolve immutable version under an already-successful START owner.

    Only prepares a binding. Caller decides when it becomes authoritative;
    this operation never enables hardware or changes active stages.
    """
    recipe = recipe if recipe is not None else catalog.library.load(recipe_id, version)
    if (recipe.recipe_id, recipe.version) != (recipe_id, version):
        raise ValueError("selected recipe identity mismatch")
    report = inspect_recipe(recipe)
    if not report.admissible_structure:
        raise ValueError('; '.join(report.problems))
    if not identity.session_id or not identity.trace_id:
        raise ValueError('existing START identity required')
    if not isinstance(safety_context, SafetyContext):
        raise ValueError('START safety context required')
    if not voltage_ceiling_v > 0:
        raise ValueError('invalid active session ceiling')
    for step in recipe.steps:
        if step['action'] == 'set' and step['params']['voltage_v'] > voltage_ceiling_v:
            raise ValueError('recipe exceeds active session voltage ceiling')
    if Path(state_path).exists():
        raise ValueError('runner state already exists; no automatic takeover')
    return ExistingRecipeBinding(RecipeSession(recipe, identity), port, safety_context,
                                 voltage_ceiling_v, state_path, journal_path,
                                 measurement_path)


async def advance_in_existing_session(
    session: RecipeSession, *, host: Any, port: Any,
    now_s: float, measurements: Mapping[str, float],
    safety_context: SafetyContext, voltage_ceiling_v: float,
    state_path: str | Path, journal_path: str | Path | None = None,
    measurement_path: str | Path | None = None,
):
    """Use production V/I caps for SET, with caller's actual recipe envelope.

    The existing session owner must provide identity, safety context, and
    voltage ceiling. Pending actions cannot be replayed on invocation.
    """
    if session.restored_inactive:
        raise RuntimeError("restored recipe session cannot execute")
    if session.state.pending is not None:
        raise RuntimeError("pending hardware action requires reconciliation")
    proposal = tick(session.recipe, session.state, now_s=now_s,
                    measurements=measurements).command
    if proposal is not None and proposal.operation == "set":
        requested_voltage = float(proposal.parameters["voltage_v"])
        if requested_voltage > float(voltage_ceiling_v):
            raise ValueError("recipe target exceeds active session voltage ceiling")
    requested_current = (float(proposal.parameters["current_a"])
                         if proposal is not None and proposal.operation == "set" else None)
    if requested_current is not None:
        capped = float(host._cap_current(requested_current))
        if capped <= 0 or capped < requested_current:
            raise ValueError("recipe target exceeds existing current cap")
    return await advance_durable_recipe_session(
        session, port=port, now_s=now_s, measurements=measurements,
        safety_context=safety_context, recipe_voltage_ceiling_v=float(voltage_ceiling_v),
        state_path=state_path, journal_path=journal_path,
        measurement_path=measurement_path,
    )
