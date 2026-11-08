"""Pure managed runtime telemetry validity classification.

Physical execution, clocks and recovery budget stay with ManagedRuntimeSafetyGuard.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rd6018_telemetry import (
    ProtectionStatus, canonical_programmed_readback, resolve_protection,
)
from runtime_safety import _binary, _finite


def managed_critical_telemetry_error(
    live: Mapping[str, Any], *,
    require_programming: bool,
    min_battery_voltage_v: float,
    max_battery_voltage_v: float,
    critical_temp_c: float,
    max_internal_temp_c: float,
) -> str | None:
    numeric_keys = ["battery_voltage", "current", "temp_ext", "temp_int"]
    if require_programming:
        numeric_keys.append("voltage")
    for key in numeric_keys:
        if _finite(live.get(key)) is None:
            return f"required telemetry {key} is missing/unavailable"
    if _binary(live.get("switch")) is None:
        return "required telemetry switch is missing/unavailable"
    if live.get("protection_code") in (None, "", "unknown", "unavailable"):
        for key in ("ovp_triggered", "ocp_triggered"):
            if _binary(live.get(key)) is None:
                return f"required telemetry {key} is missing/unavailable"
    protection = resolve_protection(live)
    if protection.status is ProtectionStatus.UNKNOWN:
        return "RD6018 protection status is unknown"
    if protection.status is ProtectionStatus.OPP:
        return "RD6018 OPP protection is tripped"
    battery_v = _finite(live.get("battery_voltage"))
    assert battery_v is not None
    if not min_battery_voltage_v <= battery_v <= max_battery_voltage_v:
        return f"battery voltage is implausible: {battery_v:.3f}V"
    temp_ext = _finite(live.get("temp_ext"))
    temp_int = _finite(live.get("temp_int"))
    assert temp_ext is not None and temp_int is not None
    if temp_ext >= critical_temp_c:
        return f"battery temperature {temp_ext:.1f}C is critical"
    if temp_int >= max_internal_temp_c:
        return f"power-supply temperature {temp_int:.1f}C is critical"
    if require_programming:
        for key in ("set_voltage", "set_current", "ovp", "ocp"):
            if canonical_programmed_readback(live, key) is None:
                if key == "set_current":
                    return "authoritative current readback V2 is missing/stale"
                return f"authoritative {key} readback V2 is missing/stale"
    return None
