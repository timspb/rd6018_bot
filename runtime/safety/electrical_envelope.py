"""Pure managed V/I envelope checks, with no device commands or clocks."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rd6018_telemetry import canonical_programmed_readback, finite_float


def managed_envelope_error(
    live: Mapping[str, Any], *,
    recipe_ceiling_v: float,
    absolute_voltage_ceiling_v: float,
    absolute_current_ceiling_a: float,
    max_stage_current_a: float,
    readback_tolerance: float,
) -> str | None:
    """Require fresh working setpoints and measured V/I within existing limits."""
    set_v = canonical_programmed_readback(live, "set_voltage")
    set_i = canonical_programmed_readback(live, "set_current")
    actual_v = finite_float(live.get("voltage"))
    actual_i = finite_float(live.get("current"))
    if None in (set_v, set_i, actual_v, actual_i):
        return "programming/readback/measured output became invalid while output was ON"
    assert set_v is not None and set_i is not None
    assert actual_v is not None and actual_i is not None

    tol = readback_tolerance
    if set_v > recipe_ceiling_v + tol:
        return f"set voltage {set_v:.3f}V exceeds recipe ceiling {recipe_ceiling_v:.3f}V"
    if set_v > absolute_voltage_ceiling_v + tol:
        return f"set voltage {set_v:.3f}V exceeds absolute ceiling"
    if actual_v > recipe_ceiling_v + tol:
        return f"measured output voltage {actual_v:.3f}V exceeds recipe ceiling {recipe_ceiling_v:.3f}V"
    if actual_v > absolute_voltage_ceiling_v + tol:
        return f"measured output voltage {actual_v:.3f}V exceeds absolute ceiling"
    if set_i <= 0 or set_i > max_stage_current_a + tol:
        return f"set current {set_i:.3f}A exceeds runtime envelope"
    if actual_i > absolute_current_ceiling_a + tol:
        return f"measured current {actual_i:.3f}A exceeds absolute working-current envelope"
    return None
