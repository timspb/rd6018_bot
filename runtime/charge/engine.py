"""Pure orchestration boundary for charge programs."""

from __future__ import annotations

from .battery import BatteryProfile
from .decisions import ActuatorIntent, ContainmentResultRequest, DomainDecision
from .intent import ChargeIntent
from .measurements import Measurements
from .program import ChargeProgram
from .registry import ProgramRegistry
from .state import ChargeState
from .strategy import ChargeStrategy, StrategyRuntimeState


class ChargeEngine:
    """Own pure phase transitions and evaluate programs without integrations."""

    TRANSITIONS = {
        "idle": {"prep", "main"},
        "prep": {"main", "stopped"},
        "main": {"main", "recovery", "mix", "cooling", "safe_wait", "done", "stopped"},
        "recovery": {"main", "safe_wait", "stopped"},
        "mix": {"mix", "mix_hold", "safe_wait", "done", "stopped"},
        "mix_hold": {"done", "stopped"},
        "safe_wait": {"main", "done", "stopped"},
        "cooling": {"main", "stopped"},
        "done": {"idle"},
        "stopped": {"idle"},
    }

    def __init__(self, battery: BatteryProfile, program: ChargeProgram | None = None, *, strategy: ChargeStrategy | None = None, registry: ProgramRegistry | None = None, program_name: str | None = None, program_config: object = None) -> None:
        self.battery = battery
        self.strategy = strategy
        if strategy is not None:
            self.program = None
            return
        if program is None:
            if registry is None or program_name is None:
                raise ValueError("program or registry/program_name is required")
            program = registry.create(program_name, battery, program_config)
        self.program = program

    def evaluate(self, state: ChargeState, measurements: Measurements) -> ChargeIntent:
        """Return the program's intent for the supplied data snapshots."""
        if self.strategy is not None:
            if not isinstance(state, StrategyRuntimeState):
                raise TypeError("ChargeStrategy execution requires StrategyRuntimeState")
            result = self.strategy.evaluate(state, measurements)
        else:
            result = self.program.evaluate(state, measurements)
        if result.next_stage is not None:
            current = str(state.stage or "idle").strip().lower()
            target = str(result.next_stage).strip().lower()
            # Generic programs may expose their own local stage labels.  Keep
            # the legacy evaluator contract for those labels; callers that
            # coordinate the canonical FSM use the strict transition() API.
            if current in self.TRANSITIONS and target in self.TRANSITIONS:
                self.transition(state, result.next_stage)
            elif current == target:
                state.stage = result.next_stage
        return result

    def transition(self, state: ChargeState, next_stage: str) -> ChargeState:
        """Apply a validated domain transition to the supplied state only."""
        target = str(next_stage).strip().lower()
        current = str(state.stage or "idle").strip().lower()
        if target not in self.TRANSITIONS.get(current, set()):
            raise ValueError(f"invalid charge transition: {current} -> {target}")
        state.stage = next_stage
        state.completed = target in {"done", "stopped"}
        return state

    def decision(self, state: ChargeState, measurements: Measurements) -> DomainDecision:
        """Return domain outputs; no output or containment owner is invoked."""
        charge_intent = self.evaluate(state, measurements)
        if charge_intent.target_voltage is None and charge_intent.target_current is None:
            return DomainDecision(state.stage, None, completed=charge_intent.completed, reason=charge_intent.reason)
        return DomainDecision(
            state.stage,
            ActuatorIntent("setpoints", charge_intent.target_voltage, charge_intent.target_current, charge_intent.reason),
            completed=charge_intent.completed,
            reason=charge_intent.reason,
        )

    @staticmethod
    def containment_request(trigger: str, reason: str) -> ContainmentResultRequest:
        return ContainmentResultRequest(trigger=trigger, reason=reason)
