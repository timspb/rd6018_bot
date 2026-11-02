"""Recipe action handoff: explicitly acknowledged, never talks to hardware.

The production ExecutionPort remains the sole hardware owner. This module
does not grant permission to energize output or resume a saved session.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping

from .recipe_engine import StepDecision
from .recipe_schema import Recipe


@dataclass(frozen=True)
class PendingAction:
    recipe_digest: str
    step_index: int
    action_id: str
    operation: str
    parameters: dict[str, float]


@dataclass(frozen=True)
class ActionReceipt:
    action_id: str
    accepted: bool
    verified: bool
    output_off: bool

def propose_action(recipe: Recipe, decision: StepDecision) -> PendingAction | None:
    """Make a stable action identity, without applying the proposed action."""
    if decision.proposed_action is None:
        return None
    if decision.state.recipe_digest != recipe.digest:
        raise ValueError("recipe revision mismatch")
    operation = decision.proposed_action
    if operation not in {"set", "off", "wait"}:
        raise ValueError("unsupported operation")
    body = {"digest": recipe.digest, "step": decision.state.step_index,
            "operation": operation, "params": decision.parameters}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return PendingAction(recipe.digest, decision.state.step_index,
                         sha256(encoded.encode("utf-8")).hexdigest(),
                         operation, dict(decision.parameters))


def acknowledge_action(pending: PendingAction, receipt: ActionReceipt) -> bool:
    """Accept only a matching verified receipt; OFF must have OFF readback."""
    if receipt.action_id != pending.action_id:
        raise ValueError("action receipt identity mismatch")
    if not receipt.accepted or not receipt.verified:
        return False
    if pending.operation == "off" and not receipt.output_off:
        return False
    return True


def may_auto_resume_from_checkpoint(*, output_confirmed_off: bool) -> bool:
    """Never automatically re-energize, regardless of checkpoint contents."""
    return False
