"""Pure adapter from an existing legacy decision result to ChargeIntent."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ..battery import BatteryProfile
from ..intent import ChargeIntent
from ..measurements import Measurements
from ..program import ChargeProgram
from ..state import ChargeState


LegacyBehavior = Callable[
    [BatteryProfile, ChargeState, Measurements],
    Mapping[str, Any],
]


class LegacyChargeProgramAdapter(ChargeProgram):
    """Adapt a pure legacy/V2 decision callable without owning integrations.

    The callable must return a decision mapping only.  It is not a controller
    instance and is never given HA, RD, output, lease, or persistence access.
    """

    def __init__(self, battery: BatteryProfile, behavior: LegacyBehavior) -> None:
        self.battery = battery
        self.behavior = behavior

    def evaluate(self, state: ChargeState, measurements: Measurements) -> ChargeIntent:
        result = self.behavior(self.battery, state, measurements)
        if not isinstance(result, Mapping):
            raise TypeError("legacy behavior must return a decision mapping")
        forbidden = {"turn_on", "turn_off", "emergency_stop", "full_reset"}
        if forbidden.intersection(result):
            raise ValueError("legacy actuator commands cannot cross the program boundary")
        return ChargeIntent(
            target_voltage=result.get("target_voltage", result.get("set_voltage")),
            target_current=result.get("target_current", result.get("set_current")),
            next_stage=result.get("next_stage", state.stage),
            completed=bool(result.get("completed", False)),
            reason=str(result.get("reason", result.get("log_event", ""))),
        )
