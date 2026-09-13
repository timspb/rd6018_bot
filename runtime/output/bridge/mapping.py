"""Pure V3-to-V2 command representation mapping; no actuator calls."""

from __future__ import annotations

from ..intent import OutputAction, SafeOutputIntent
from .contract import LegacyActuatorCommand


def map_safe_output_intent(intent: SafeOutputIntent) -> LegacyActuatorCommand:
    parameters = {}
    if intent.target_voltage is not None:
        parameters["voltage"] = intent.target_voltage
    if intent.target_current is not None:
        parameters["current"] = intent.target_current
    return LegacyActuatorCommand(intent.action.value, parameters)
