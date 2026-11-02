"""Opt-in recipe adapter to the existing ExecutionPort; no second hardware owner."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.execution_intent.models import ExecutionIntent, SafetyContext
from runtime.charge.programs.recipe_dispatch import ActionReceipt, PendingAction


@dataclass(frozen=True)
class RecipeExecutionIdentity:
    session_id: str
    trace_id: str


async def execute_recipe_action(*, port: Any, pending: PendingAction,
                                identity: RecipeExecutionIdentity,
                                admitted: bool = False) -> ActionReceipt:
    """Execute only within an externally admitted, already-active session.

    Setpoints never enable the output; OFF uses the existing verified OFF path.
    Startup and resume still belong exclusively to the production START owner.
    """
    if not identity.session_id or not identity.trace_id:
        raise ValueError("verified recipe session identity required")
    if not admitted:
        raise PermissionError("recipe not admitted by session owner")
    if pending.operation == "wait":
        return ActionReceipt(pending.action_id, True, True, False)
    if pending.operation not in {"set", "off"}:
        raise ValueError("unsupported recipe operation")
    if pending.operation == "set":
        v, i = pending.parameters["voltage_v"], pending.parameters["current_a"]
    else:
        v, i = 0.0, 0.0
    intent = ExecutionIntent(
        requested_voltage_v=v, requested_current_a=i,
        requested_mode="RECIPE_ACTIVE" if pending.operation == "set" else "RECIPE_OFF",
        source_decision_id=pending.action_id,
        safety_context=SafetyContext(
            telemetry_state="FRESH", lease_state="V2_PHYSICAL_OWNER",
            verification_state="REQUIRED",
            limits_reference="recipe_prevalidated_existing_session",
        ),
    )
    if pending.operation == "off":
        result = await port.disable(intent, identity=identity, reason="recipe_step_off")
    else:
        result = await port.apply_intent(intent, identity=identity)
    return ActionReceipt(
        action_id=pending.action_id,
        accepted=bool(result.accepted),
        verified=bool(result.verified),
        output_off=bool(result.verified) if pending.operation == "off" else False,
    )
