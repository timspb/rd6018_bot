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
                                safety_context: SafetyContext,
                                restart_limits: tuple[float, float, float] | None = None) -> ActionReceipt:
    """Execute only within an externally admitted, already-active session.

    Setpoints never enable the output; OFF uses the existing verified OFF path.
    Startup and resume still belong exclusively to the production START owner.
    """
    if not identity.session_id or not identity.trace_id:
        raise ValueError("existing charge session identity required")
    if not isinstance(safety_context, SafetyContext):
        raise ValueError("existing execution safety context required")
    if pending.operation == "wait":
        return ActionReceipt(pending.action_id, True, True, False)
    if pending.operation not in {"set", "off"}:
        raise ValueError("unsupported recipe operation")
    if pending.operation == "set":
        if getattr(port, "guarded_restore_activated_off", False):
            return ActionReceipt(pending.action_id, False, False, False)
        v, i = pending.parameters["voltage_v"], pending.parameters["current_a"]
    else:
        v, i = 0.0, 0.0
    intent = ExecutionIntent(
        requested_voltage_v=v, requested_current_a=i,
        requested_mode="RECIPE_ACTIVE" if pending.operation == "set" else "RECIPE_OFF",
        source_decision_id=pending.action_id,
        safety_context=safety_context,
    )
    if pending.operation == "off":
        result = await port.disable(intent, identity=identity, reason="recipe_step_off")
    else:
        # Reuse the existing physical owner for OFF -> ON, never fabricate OVP/OCP.
        owner = getattr(port, "execution_owner", None)
        if owner is not None:
            live = await owner.get_all_live()
            switch = str(live.get("switch", "")).lower()
            if switch not in {"on", "true", "1", "off", "false", "0"}:
                return ActionReceipt(pending.action_id, False, False, False)
            if switch in {"off", "false", "0"}:
                if restart_limits is None:
                    return ActionReceipt(pending.action_id, False, False, False)
                ovp_v, ocp_a, ceiling_v = restart_limits
                result = await port.enable(intent, identity=identity, ovp_v=ovp_v,
                                           ocp_a=ocp_a, recipe_voltage_ceiling_v=ceiling_v)
            else:
                result = await port.apply_intent(intent, identity=identity)
        else:
            result = await port.apply_intent(intent, identity=identity)
    return ActionReceipt(
        action_id=pending.action_id,
        accepted=bool(result.accepted),
        verified=bool(result.verified),
        output_off=bool(result.verified) if pending.operation == "off" else False,
    )
