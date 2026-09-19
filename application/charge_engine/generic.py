"""Generic provider, registry and evaluator for arbitrary V3 ChargeProgram objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Protocol, Tuple

from application.charge_program import ChargeProgram, Phase, TransitionRule

from .models import BatteryState, ChargeDecision, TelemetrySnapshot


class ChargeProgramProvider(Protocol):
    """Program plugin contract; implementations own their metadata and transitions."""

    @property
    def program(self) -> ChargeProgram: ...

    def metadata(self) -> Tuple[Tuple[str, str], ...]: ...

    def phases(self) -> Tuple[Phase, ...]: ...

    def conditions(self) -> Tuple[str, ...]: ...

    def targets(self) -> Tuple[str, ...]: ...

    def transitions(self) -> Tuple[TransitionRule, ...]: ...


@dataclass(frozen=True)
class StaticChargeProgramProvider:
    """Adapter for a data-only ChargeProgram; no infrastructure dependency."""

    program: ChargeProgram

    def metadata(self) -> Tuple[Tuple[str, str], ...]:
        return (("program_id", self.program.program_id), ("mode", self.program.mode.value))

    def phases(self) -> Tuple[Phase, ...]:
        return self.program.phases

    def conditions(self) -> Tuple[str, ...]:
        return tuple(condition.name for condition in self.program.conditions)

    def targets(self) -> Tuple[str, ...]:
        return tuple(phase.phase_id for phase in self.program.phases)

    def transitions(self) -> Tuple[TransitionRule, ...]:
        return self.program.transitions


class ChargeProgramRegistry:
    """Registry for independent program plugins."""

    def __init__(self) -> None:
        self._providers: Dict[str, ChargeProgramProvider] = {}

    def register(self, provider: ChargeProgramProvider) -> None:
        program_id = str(provider.program.program_id).strip()
        self.validate(provider)
        if program_id in self._providers:
            raise ValueError(f"program already registered: {program_id}")
        self._providers[program_id] = provider

    def unregister(self, program_id: str) -> ChargeProgramProvider:
        try:
            return self._providers.pop(str(program_id).strip())
        except KeyError as exc:
            raise KeyError(f"unknown charge program: {program_id}") from exc

    def lookup(self, program_id: str) -> ChargeProgramProvider:
        try:
            return self._providers[str(program_id).strip()]
        except KeyError as exc:
            raise KeyError(f"unknown charge program: {program_id}") from exc

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    @staticmethod
    def validate(provider: ChargeProgramProvider) -> None:
        program = provider.program
        if not str(program.program_id).strip():
            raise ValueError("program_id is required")
        phase_ids = [phase.phase_id for phase in provider.phases()]
        if not phase_ids or len(set(phase_ids)) != len(phase_ids):
            raise ValueError("program phases must be non-empty and unique")
        phase_set = set(phase_ids)
        for transition in provider.transitions():
            # Lifecycle states may be represented only by a transition rule;
            # the program still owns the transition and the engine remains generic.
            if transition.source_phase not in phase_set and not transition.source_phase:
                raise ValueError("transition source phase is required")
            if not transition.target_phase:
                raise ValueError("transition target phase is required")
        if set(provider.targets()) != phase_set:
            raise ValueError("provider targets must describe all program phases")


class GenericChargeEngine:
    """Evaluate any registered program using only its generic contract."""

    def __init__(self, program: ChargeProgram | None = None) -> None:
        self.program = program

    def evaluate(self, *args) -> ChargeDecision:
        if self.program is None:
            program, state, telemetry = args
        else:
            state, telemetry = args
            program = self.program
        phase_id = str(state.phase.value if hasattr(state.phase, "value") else state.phase).lower()
        provider = StaticChargeProgramProvider(program)
        ChargeProgramRegistry.validate(provider)
        phases = {phase.phase_id: phase for phase in provider.phases()}
        phase = phases.get(phase_id)
        transitions = provider.transitions()

        if not telemetry.complete:
            return ChargeDecision(
                current_phase=state.phase,
                desired_voltage_v=None,
                desired_current_a=None,
                reason="required telemetry is missing or stale",
                conditions=("fresh telemetry required by engine contract",),
                next_transition_criteria=("receive complete fresh telemetry",),
                program_id=program.program_id,
                confidence="UNKNOWN",
                decision_id=f"{program.program_id}:{phase_id}:telemetry-missing",
            )

        next_phase = None
        transition_reason = "phase continues"
        criteria = tuple(condition.name for condition in phase.conditions) if phase else ()
        for transition in transitions:
            if transition.source_phase == phase_id and state.condition(transition.condition_key):
                next_phase = type(state.phase)(transition.target_phase.upper()) if hasattr(state.phase, "value") else transition.target_phase
                transition_reason = f"transition condition confirmed: {transition.condition_key}"
                break

        if phase is None:
            return ChargeDecision(
                current_phase=state.phase,
                desired_voltage_v=None,
                desired_current_a=None,
                reason=f"no {phase_id.upper()} policy is present in ChargeProgram" if next_phase is None else transition_reason,
                conditions=criteria,
                next_transition_criteria=tuple(rule.condition_key for rule in transitions if rule.source_phase == phase_id),
                next_phase=next_phase,
                program_id=program.program_id,
                confidence="HIGH" if next_phase is not None else "UNKNOWN",
                decision_id=f"{program.program_id}:{phase_id}:{transition_reason}",
            )

        if not phase.emits_setpoints:
            return ChargeDecision(
                current_phase=state.phase,
                desired_voltage_v=None,
                desired_current_a=None,
                reason=transition_reason,
                conditions=criteria,
                next_transition_criteria=tuple(rule.condition_key for rule in transitions if rule.source_phase == phase.phase_id),
                next_phase=next_phase,
                program_id=program.program_id,
                confidence="HIGH",
                decision_id=f"{program.program_id}:{phase.phase_id}:{transition_reason}",
            )
        return ChargeDecision(
            current_phase=state.phase,
            desired_voltage_v=float(phase.voltage.target.value),
            desired_current_a=float(phase.current.target.value),
            reason=transition_reason,
            conditions=criteria,
            next_transition_criteria=tuple(rule.condition_key for rule in transitions if rule.source_phase == phase.phase_id),
            next_phase=next_phase,
            program_id=program.program_id,
            confidence="HIGH",
            decision_id=f"{program.program_id}:{phase.phase_id}:{transition_reason}",
        )
