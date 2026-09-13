"""Pure orchestration boundary for charge programs."""

from __future__ import annotations

from .battery import BatteryProfile
from .intent import ChargeIntent
from .measurements import Measurements
from .program import ChargeProgram
from .registry import ProgramRegistry
from .state import ChargeState


class ChargeEngine:
    """Evaluate an active program without owning any runtime integration."""

    def __init__(self, battery: BatteryProfile, program: ChargeProgram | None = None, *, registry: ProgramRegistry | None = None, program_name: str | None = None, program_config: object = None) -> None:
        self.battery = battery
        if program is None:
            if registry is None or program_name is None:
                raise ValueError("program or registry/program_name is required")
            program = registry.create(program_name, battery, program_config)
        self.program = program

    def evaluate(self, state: ChargeState, measurements: Measurements) -> ChargeIntent:
        """Return the program's intent for the supplied data snapshots."""
        return self.program.evaluate(state, measurements)
