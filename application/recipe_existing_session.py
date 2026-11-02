"""Advance a recipe within the already-owned production charging session.

This is a callable adapter, not a new loop, START path, or session owner.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from application.execution_intent.models import SafetyContext
from application.recipe_restart_limits import existing_start_limits
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


async def advance_in_existing_session(
    session: RecipeSession, *, host: Any, port: Any,
    now_s: float, measurements: Mapping[str, float],
    safety_context: SafetyContext, voltage_ceiling_v: float,
    state_path: str | Path, journal_path: str | Path | None = None,
    measurement_path: str | Path | None = None,
):
    """Use production START offsets for SET, with caller's actual envelope.

    The existing session owner must provide identity, safety context, and
    voltage ceiling. Pending actions cannot be replayed on invocation.
    """
    if session.restored_inactive:
        raise RuntimeError("restored recipe session cannot execute")
    if session.state.pending is not None:
        raise RuntimeError("pending hardware action requires reconciliation")
    proposal = tick(session.recipe, session.state, now_s=now_s,
                    measurements=measurements).command
    limits = None
    if proposal is not None and proposal.operation == "set":
        limits = existing_start_limits(
            host,
            voltage_v=proposal.parameters["voltage_v"],
            current_a=proposal.parameters["current_a"],
            voltage_ceiling_v=voltage_ceiling_v,
        )
    return await advance_durable_recipe_session(
        session, port=port, now_s=now_s, measurements=measurements,
        safety_context=safety_context, restart_limits=limits,
        state_path=state_path, journal_path=journal_path,
        measurement_path=measurement_path,
    )
