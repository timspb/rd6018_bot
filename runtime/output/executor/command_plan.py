"""Physical command plan models. Plans are inspectable and never executable."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.output.intent import OutputAction, SafeOutputIntent


@dataclass(frozen=True)
class PhysicalCommandStep:
    name: str
    requires_readback: bool = False


@dataclass(frozen=True)
class PhysicalCommandPlan:
    intent: SafeOutputIntent
    steps: tuple[PhysicalCommandStep, ...]
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("command plan must remain non-executable in this phase")
        if not self.steps:
            raise ValueError("command plan must contain steps")


def build_command_plan(intent: SafeOutputIntent) -> PhysicalCommandPlan:
    if intent.action is OutputAction.ENABLE:
        names = ("prepare", "set_voltage", "set_current", "set_ovp", "set_ocp", "readback_compare", "enable")
    elif intent.action is OutputAction.DISABLE:
        names = ("disable", "read_output_state", "confirm_off", "reset_protection")
    elif intent.action is OutputAction.RESET_PROTECTION:
        names = ("reset_ovp", "reset_ocp", "readback_compare")
    else:
        names = (intent.action.value,)
    steps = tuple(PhysicalCommandStep(name, name in {"readback_compare", "read_output_state", "confirm_off"}) for name in names)
    return PhysicalCommandPlan(intent, steps)
