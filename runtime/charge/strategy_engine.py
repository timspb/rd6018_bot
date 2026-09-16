"""Pure strategy runtime facade."""

from __future__ import annotations

from .battery import BatteryProfile
from .intent import ChargeIntent
from .measurements import Measurements
from .state import ChargeState
from .strategy import ChargeStrategy, StrategyRuntimeState


class StrategyEngine:
    """Own termination, Delta, hold and timer decisions without side effects."""

    def __init__(self, battery: BatteryProfile) -> None:
        if battery.recipe is None:
            raise ValueError("StrategyEngine requires a validated recipe")
        self.strategy = ChargeStrategy(battery, battery.recipe)

    def evaluate(self, state: ChargeState | StrategyRuntimeState, measurements: Measurements, *, mix_mode: str | None = None) -> ChargeIntent:
        runtime_state = state if isinstance(state, StrategyRuntimeState) else StrategyRuntimeState(stage=state.stage or "main")
        return self.strategy.evaluate(runtime_state, measurements, mix_mode=mix_mode)
