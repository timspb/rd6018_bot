"""Non-actuating production-tick observer for an explicitly attached recipe.

Keeps the historical controller authoritative; never starts, sets or stops hardware.
"""
from __future__ import annotations
from typing import Any
from runtime.charge.programs.recipe_measurements import record_measurement

def observe_recipe_tick(host: Any, *, timestamp_s: float, voltage: float,
                        current: float, temperature: float | None) -> None:
    binding = getattr(host, "_recipe_observation_binding", None)
    if binding is None:
        return
    recipe, session_id, path = binding
    values = {"voltage": voltage, "current": current}
    if temperature is not None:
        values["temperature"] = temperature
    record_measurement(path, recipe=recipe, session_id=session_id,
                       timestamp_s=timestamp_s, values=values)
