"""HANDS_OFF, adopted MIX, and external ownership button rules."""
from application.operator_actions import OperatorAction as A
from .common import action_view

def hands_off(*, output_on: bool):
    if output_on:
        return action_view((A.ADOPT_MIX, A.DISABLE_OUTPUT), (), "hands_off")
    return action_view((A.START_CHARGE, A.RETURN_PB_CONTROL),
                       (A.SELECT_PROFILE,), "hands_off")

def adopted_mix(*, interrupted: bool):
    if interrupted:
        return action_view((A.ADOPT_MIX, A.SHOW_LOG, A.SHOW_DIAGNOSTICS),
                           (A.START_CHARGE, A.STOP_CHARGE), "interrupted")
    return action_view((A.STOP_MIX, A.SHOW_LOG, A.SHOW_DIAGNOSTICS),
                       (A.START_CHARGE, A.SELECT_PROFILE), "adopted_mix")
