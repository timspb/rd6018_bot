"""Runtime-local, read-only service for the V3 charge domain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .battery import BatteryProfile
from .engine import ChargeEngine
from .intent import ChargeIntent
from .measurements import Measurements
from .registry import ProgramRegistry
from .state import ChargeState


@dataclass(frozen=True)
class ChargeRuntimeSnapshot:
    active_program: str
    battery_profile: BatteryProfile
    intent: ChargeIntent
    timestamp: float


class ChargeService:
    """Select and evaluate domain programs; never applies their intents."""

    def __init__(self, registry: ProgramRegistry, clock: Callable[[], float]) -> None:
        self.registry = registry
        self.clock = clock

    def evaluate(
        self,
        battery: BatteryProfile,
        program_name: str,
        program_config: Any,
        state: ChargeState,
        measurements: Measurements,
    ) -> ChargeRuntimeSnapshot:
        engine = ChargeEngine(
            battery,
            registry=self.registry,
            program_name=program_name,
            program_config=program_config,
        )
        return ChargeRuntimeSnapshot(
            active_program=program_name.strip().lower(),
            battery_profile=battery,
            intent=engine.evaluate(state, measurements),
            timestamp=self.clock(),
        )
