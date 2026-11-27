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
        from .operator_button_rules.snapshot import actions_for_generic_state
        return actions_for_generic_state(
            state, safety_allowed=safety_allowed, pause_allowed=pause_allowed,
        )
