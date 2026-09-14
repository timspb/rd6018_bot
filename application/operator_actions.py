"""Read-only operator capability matrix; no callback or actuator knowledge."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class OperatorAction(str, Enum):
    START_CHARGE = "start_charge"
    SELECT_PROFILE = "select_profile"
    STOP_CHARGE = "stop_charge"
    PAUSE_CHARGE = "pause_charge"
    RESUME_CHARGE = "resume_charge"
    SHOW_LOG = "show_log"
    SHOW_GRAPH = "show_graph"
    SHOW_DIAGNOSTICS = "show_diagnostics"
    ACK = "ack"
    ADOPT_MIX = "adopt_mix"
    STOP_MIX = "stop_mix"
    DISABLE_OUTPUT = "disable_output"
    REAUTHORIZE_MANUAL = "reauthorize_manual"
    DISCARD_MANUAL = "discard_manual"
    RETURN_PB_CONTROL = "return_pb_control"


@dataclass(frozen=True)
class OperatorActionSpec:
    action: OperatorAction
    parameters: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class OperatorActionsView:
    available_actions: tuple[OperatorActionSpec, ...] = ()
    disabled_actions: tuple[OperatorAction, ...] = ()
    reasons: Mapping[str, str] = field(default_factory=dict)

    def allows(self, action: OperatorAction) -> bool:
        return any(item.action is action for item in self.available_actions)

    @classmethod
    def for_state(cls, state: str, *, safety_allowed: bool, pause_allowed: bool = False) -> "OperatorActionsView":
        if state == "IDLE" and safety_allowed:
            # Profile selection lives inside the single charge-modes workspace;
            # do not duplicate an independent battery/profile entry on the panel.
            available = (OperatorAction.START_CHARGE, OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS)
            disabled = (OperatorAction.STOP_CHARGE, OperatorAction.PAUSE_CHARGE, OperatorAction.RESUME_CHARGE)
        elif state == "CHARGING":
            values = [OperatorAction.STOP_CHARGE, OperatorAction.SHOW_LOG, OperatorAction.SHOW_GRAPH]
            if pause_allowed:
                values.insert(1, OperatorAction.PAUSE_CHARGE)
            available = tuple(values)
            disabled = (OperatorAction.START_CHARGE, OperatorAction.SELECT_PROFILE)
        else:
            available = (OperatorAction.SHOW_DIAGNOSTICS, OperatorAction.ACK)
            disabled = (OperatorAction.START_CHARGE, OperatorAction.STOP_CHARGE, OperatorAction.SELECT_PROFILE)
        reasons = {action.value: "not_available_in_current_state" for action in disabled}
        if state == "FAULT":
            reasons[OperatorAction.START_CHARGE.value] = "safety_state"
        return cls(tuple(OperatorActionSpec(action) for action in available), disabled, reasons)
