"""Pure read-only RD live telemetry extraction for HMI.

Input precedence is deliberately unchanged: use V2 temperature fields first,
then historical HA names. This function has no freshness or safety authority.
"""
from __future__ import annotations
from typing import Any, Mapping
from .hmi_values import _finite, _on


def _first_finite(live: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        result = _finite(live.get(key))
        if result is not None:
            return result
    return None


def _live_measurements(live: Mapping[str, Any]) -> tuple[
    bool, float | None, float | None, float | None,
    float | None, float | None, float | None, float | None,
]:
    return (
        _on(live.get("switch")),
        _finite(live.get("battery_voltage")),
        _finite(live.get("current")),
        _finite(live.get("power")),
        _first_finite(live, ("temp_ext_v2", "temp_ext")),
        _first_finite(live, ("temp_int_v2", "temp_int", "psu_temperature", "power_supply_temperature")),
        _finite(live.get("set_voltage")),
        _finite(live.get("set_current")),
    )
