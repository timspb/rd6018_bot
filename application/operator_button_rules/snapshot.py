"""Snapshot-only actions: the read model has no live HMI session identity."""
from application.operator_actions import OperatorAction, OperatorActionSpec, OperatorActionsView

def actions_for_generic_state(state: str, *, safety_allowed: bool, pause_allowed: bool = False) -> OperatorActionsView:
        if state == "IDLE":
            # Profile selection lives inside the single charge-modes workspace;
            # do not duplicate an independent battery/profile entry on the panel.
            # There is no active session to inspect in IDLE. Logs/details remain
            # available from their dedicated workspaces once a session exists.
            # START_CHARGE is a navigation capability here: it opens the
            # read-only charge/profile workspace.  The actual start route
            # performs its own current safety/preflight authorization.
            available = (OperatorAction.START_CHARGE,)
            disabled = (
                OperatorAction.STOP_CHARGE,
                OperatorAction.PAUSE_CHARGE,
                OperatorAction.RESUME_CHARGE,
                OperatorAction.SHOW_LOG,
                OperatorAction.SHOW_DIAGNOSTICS,
            )
        elif state == "CHARGING":
            values = [OperatorAction.STOP_CHARGE, OperatorAction.SHOW_LOG, OperatorAction.SHOW_GRAPH]
            if pause_allowed:
                values.insert(1, OperatorAction.PAUSE_CHARGE)
            available = tuple(values)
            disabled = (OperatorAction.START_CHARGE, OperatorAction.SELECT_PROFILE)
        elif state == "HANDS_OFF":
            # HANDS_OFF is an ownership state, not a safety fault.  Opening the
            # charge-modes screen is navigation-only; it is not permission to
            # start a Pb program.
            available = (OperatorAction.START_CHARGE, OperatorAction.RETURN_PB_CONTROL)
            disabled = (
                OperatorAction.SELECT_PROFILE,
                OperatorAction.STOP_CHARGE,
                OperatorAction.PAUSE_CHARGE,
                OperatorAction.RESUME_CHARGE,
            )
        else:
            available = (OperatorAction.SHOW_DIAGNOSTICS, OperatorAction.ACK)
            disabled = (OperatorAction.START_CHARGE, OperatorAction.STOP_CHARGE, OperatorAction.SELECT_PROFILE)
        reasons = {action.value: "not_available_in_current_state" for action in disabled}
        if state == "IDLE" and not safety_allowed:
            reasons[OperatorAction.START_CHARGE.value] = "start_requires_current_safety_preflight"
        if state == "FAULT":
            reasons[OperatorAction.START_CHARGE.value] = "safety_state"
        return OperatorActionsView(tuple(OperatorActionSpec(action) for action in available), disabled, reasons)
