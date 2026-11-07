"""The one operator-action selector used by application and Telegram.

Edit the small focused rule files for state-specific button availability.
The Telegram keyboard renderer only renders the chosen actions.
"""
from application.operator_actions import OperatorActionsView
from . import session, external

def actions_for_hmi(state, *, paused: bool | None = None) -> OperatorActionsView:
    process = getattr(getattr(state, "process_state", None), "value", "")
    authority = getattr(getattr(state, "authority", None), "value", "")
    output_on = bool(getattr(state, "output_on", False))
    if process == "idle" and bool(getattr(state, "manual_interrupted", False)):
        return session.interrupted_manual()
    if process == "hands_off":
        return external.hands_off(output_on=output_on)
    if process in {"adopted_mix", "interrupted"}:
        return external.adopted_mix(interrupted=(process == "interrupted"))
    if process == "storage":
        return session.storage()
    if process in {"running", "paused"} and authority in {"auto", "manual"}:
        return session.running(paused=process == "paused" if paused is None else paused)
    if process == "idle":
        return OperatorActionsView.for_state("IDLE", safety_allowed=True)
    return OperatorActionsView.for_state("FAULT", safety_allowed=False)

def actions_for_snapshot(snapshot) -> OperatorActionsView:
    state = snapshot.state
    if state == "IDLE" and bool(getattr(snapshot, "manual_interrupted", False)):
        return session.interrupted_manual()
    if state == "HANDS_OFF":
        return external.hands_off(output_on=bool(snapshot.snapshot.output.get("enabled")))
    return OperatorActionsView.for_state(
        state, safety_allowed=snapshot.snapshot.safety.allowed, pause_allowed=False,
    )
