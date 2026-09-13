"""ChargeStrategy composition: Main/Recovery/Mix only."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..intent import ChargeIntent
from ..measurements import Measurements
from .main import MainPolicy, MainFallbackPolicy
from .mix import MixPolicy
from .recovery import RecoveryPolicy

if TYPE_CHECKING:
    from ..battery import BatteryProfile


@dataclass
class StrategyRuntimeState:
    stage: str = "main"
    tail_started_at: float | None = None
    plateau_started_at: float | None = None
    recovery: object | None = None
    stage_started_at: float | None = None
    history: list = field(default_factory=list)


@dataclass(frozen=True)
class ChargeRecipe:
    main: MainPolicy
    recovery: RecoveryPolicy
    mix: MixPolicy
    fallback: MainFallbackPolicy | None = None


class ChargeStrategy:
    """Pure strategy orchestrator; it produces intents and never actuates."""

    def __init__(self, battery: "BatteryProfile", recipe: ChargeRecipe) -> None:
        self.battery = battery
        self.recipe = recipe

    def evaluate(self, state: StrategyRuntimeState, measurements: Measurements, *, mix_mode: str | None = None) -> ChargeIntent:
        if state.stage_started_at is None:
            state.stage_started_at = measurements.time
        if mix_mode is not None or state.stage == self.recipe.mix.config.cc.active_stage:
            result = self.recipe.mix.evaluate(mix_mode or "CV", measurements)
        elif state.stage == self.recipe.recovery.config.recovery_stage:
            result = self.recipe.recovery.return_to_main(self.recipe.main.config.target_voltage, self.recipe.main.config.target_current)
        else:
            if self.recipe.fallback is not None and state.stage_started_at is not None and measurements.time is not None:
                fallback = self.recipe.fallback.evaluate(
                    measurements.time - state.stage_started_at,
                    is_cv=measurements.voltage is not None and measurements.voltage >= self.recipe.main.config.target_voltage,
                    current=measurements.current,
                )
                if fallback is not None:
                    result = fallback
                else:
                    result = self.recipe.main.evaluate(state, measurements, self.recipe.recovery)
            else:
                result = self.recipe.main.evaluate(state, measurements, self.recipe.recovery)
        if result.next_stage and result.next_stage != state.stage:
            state.stage_started_at = measurements.time
            if result.next_stage != self.recipe.main.config.main_stage:
                state.history.clear()
        state.stage = result.next_stage or state.stage
        return result
