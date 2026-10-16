"""Pure strategy runtime facade."""

from __future__ import annotations

from .battery import BatteryProfile
from .intent import ChargeIntent
from .measurements import Measurements
from .state import ChargeState
from .strategy import ChargeStrategy, StrategyRuntimeState
from .strategy.mix_current_evidence import MixClipEvidence


class StrategyEngine:
    """Own termination, Delta, hold and timer decisions without side effects."""

    def __init__(self, battery: BatteryProfile) -> None:
        if battery.recipe is None:
            raise ValueError("StrategyEngine requires a validated recipe")
        self.strategy = ChargeStrategy(battery, battery.recipe)

    def evaluate(
        self, state: ChargeState | StrategyRuntimeState, measurements: Measurements, *,
        mix_mode: str | None = None, current_limit_clipped: bool = False,
        mix_clip_evidence: MixClipEvidence | None = None,
        adaptive_ratchet_active: bool = False,
    ) -> ChargeIntent:
        runtime_state = state if isinstance(state, StrategyRuntimeState) else StrategyRuntimeState(stage=state.stage or "main")
        return self.strategy.evaluate(
            runtime_state, measurements, mix_mode=mix_mode,
            current_limit_clipped=current_limit_clipped,
            mix_clip_evidence=mix_clip_evidence,
            adaptive_ratchet_active=adaptive_ratchet_active,
        )
