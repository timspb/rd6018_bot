"""Managed charge, manual session, and interrupted Manual button rules."""
from application.operator_actions import OperatorAction as A
from .common import action_view

def interrupted_manual():
    return action_view((A.REAUTHORIZE_MANUAL, A.DISCARD_MANUAL),
                       (A.START_CHARGE, A.STOP_CHARGE), "manual_interrupted")

def running(*, paused: bool):
    return action_view(
        (A.RESUME_CHARGE if paused else A.PAUSE_CHARGE,
         A.STOP_CHARGE, A.SHOW_LOG, A.SHOW_GRAPH, A.SHOW_DIAGNOSTICS),
        (A.START_CHARGE, A.SELECT_PROFILE), "charging",
    )

def storage():
    return action_view((A.SHOW_LOG, A.SHOW_DIAGNOSTICS),
                       (A.START_CHARGE, A.STOP_CHARGE), "storage")
