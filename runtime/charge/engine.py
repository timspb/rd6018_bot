"""Pure orchestration boundary for charge programs."""

from __future__ import annotations

from .battery import BatteryProfile
from .intent import ChargeIntent
from .measurements import Measurements
from .program import ChargeProgram
from .state import ChargeState


class ChargeEngine:
    """Evaluate an active program without owning any runtime integration."""

    def __init__(self, battery: BatteryProfile, program: ChargeProgram) -> None:
        self.battery = battery
        self.program = program

    def evaluate(self, state: ChargeState, measurements: Measurements) -> ChargeIntent:
        """Return the program's intent for the supplied data snapshots."""
        return self.program.evaluate(state, measurements)
