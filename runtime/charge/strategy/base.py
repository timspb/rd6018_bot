"""ChargeStrategy composition: Main/Recovery/Mix only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..intent import ChargeIntent
from ..measurements import Measurements
from .main import MainPolicy
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


@dataclass(frozen=True)
class ChargeRecipe:
    main: MainPolicy
    recovery: RecoveryPolicy
    mix: MixPolicy


class ChargeStrategy:
    """Pure strategy orchestrator; it produces intents and never actuates."""

    def __init__(self, battery: "BatteryProfile", recipe: ChargeRecipe) -> None:
        self.battery = battery
        self.recipe = recipe

    def evaluate(self, state: StrategyRuntimeState, measurements: Measurements, *, mix_mode: str | None = None) -> ChargeIntent:
        if mix_mode is not None or state.stage == self.recipe.mix.config.cc.active_stage:
            result = self.recipe.mix.evaluate(mix_mode or "CV", measurements)
        elif state.stage == self.recipe.recovery.config.recovery_stage:
            result = self.recipe.recovery.return_to_main(self.recipe.main.config.target_voltage, self.recipe.main.config.target_current)
        else:
            result = self.recipe.main.evaluate(state, measurements, self.recipe.recovery)
        state.stage = result.next_stage or state.stage
        return result
