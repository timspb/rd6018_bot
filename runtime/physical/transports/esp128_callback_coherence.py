"""Pure ESP Native reconnect batch coherence; no connection or safety authority.

The transport uses this one rule both while waiting for the initial callback
batch and before clearing the original connection-loss epoch.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REQUIRED_NATIVE_CALLBACKS = (
    "output_state", "voltage", "current", "battery_voltage",
    "configured_voltage", "configured_current", "ovp", "ocp",
    "temp_int", "temp_ext",
)


def native_batch_complete(
    configured: Mapping[str, Any],
    readings: Mapping[str, tuple[Any, Mapping[str, Any]]],
) -> bool:
    """Require fresh independent readings for all configured critical streams."""
    for name in REQUIRED_NATIVE_CALLBACKS:
        if name not in configured:
            continue
        value, meta = readings.get(name, (None, {}))
        age = meta.get("age_s")
        if (value is None or meta.get("status") != "ok"
                or not isinstance(age, (int, float)) or isinstance(age, bool)
                or not 0 <= age <= 8):
            return False
    return True
