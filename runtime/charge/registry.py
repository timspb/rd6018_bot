"""Program lookup and construction registry."""

from __future__ import annotations

from typing import Any, Callable, Dict

from .battery import BatteryProfile
from .program import ChargeProgram


ProgramFactory = Callable[[BatteryProfile, Any], ChargeProgram]


class ProgramRegistry:
    """Register, look up and create pure charge programs."""

    def __init__(self) -> None:
        self._factories: Dict[str, ProgramFactory] = {}

    def register(self, name: str, factory: ProgramFactory) -> None:
        key = str(name).strip().lower()
        if not key:
            raise ValueError("program name must not be empty")
        if key in self._factories:
            raise ValueError(f"program already registered: {key}")
        self._factories[key] = factory

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def get(self, name: str) -> ProgramFactory:
        key = str(name).strip().lower()
        try:
            return self._factories[key]
        except KeyError as exc:
            raise KeyError(f"unknown charge program: {key}") from exc

    def create(self, name: str, battery: BatteryProfile, config: Any) -> ChargeProgram:
        return self.get(name)(battery, config)

    @classmethod
    def with_defaults(cls) -> "ProgramRegistry":
        from .programs import DeltaProgram, ManualProgram, MinimumProgram

        registry = cls()
        registry.register("manual", ManualProgram)
        registry.register("minimum", MinimumProgram)
        registry.register("delta", DeltaProgram)
        return registry
