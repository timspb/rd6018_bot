"""Pure comparison of legacy and V3 charge decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from ..battery import BatteryProfile
from ..engine import ChargeEngine
from ..intent import ChargeIntent
from ..measurements import Measurements
from ..state import ChargeState


class ComparisonResult(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"


@dataclass(frozen=True)
class DecisionComparison:
    legacy: ChargeIntent
    v3: ChargeIntent
    result: ComparisonResult

    @property
    def mismatches(self) -> tuple[str, ...]:
        fields = ("target_voltage", "target_current", "next_stage", "completed", "reason")
        return tuple(field for field in fields if getattr(self.legacy, field) != getattr(self.v3, field))


class ChargeDecisionShadow:
    """Compare a legacy result with a V3 engine result without side effects."""

    def __init__(self, battery: BatteryProfile, engine: ChargeEngine) -> None:
        self.battery = battery
        self.engine = engine

    def compare(
        self,
        legacy_intent: ChargeIntent,
        state: ChargeState,
        measurements: Measurements,
    ) -> DecisionComparison:
        v3_intent = self.engine.evaluate(state, measurements)
        result = ComparisonResult.MATCH if legacy_intent == v3_intent else ComparisonResult.MISMATCH
        return DecisionComparison(legacy_intent, v3_intent, result)
