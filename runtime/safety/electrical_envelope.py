"""Pure managed electrical-envelope checks, no device commands or clocks."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rd6018_telemetry import (
    ProtectionStatus, canonical_programmed_readback, finite_float, resolve_protection,
)


def managed_envelope_error(
    live: Mapping[str, Any], *,
    recipe_ceiling_v: float,
    absolute_voltage_ceiling_v: float,
    absolute_current_ceiling_a: float,
    absolute_ovp_ceiling_v: float,
    absolute_ocp_ceiling_a: float,
    max_stage_current_a: float,
    readback_tolerance: float,
    protection_margin: float,
) -> str | None:
    protection = resolve_protection(live)
    if protection.status in {ProtectionStatus.OVP, ProtectionStatus.OCP}:
        return None

    set_v = canonical_programmed_readback(live, "set_voltage")
    set_i = canonical_programmed_readback(live, "set_current")
    ovp = canonical_programmed_readback(live, "ovp")
    ocp = canonical_programmed_readback(live, "ocp")
    actual_v = finite_float(live.get("voltage"))
    actual_i = finite_float(live.get("current"))
    if None in (set_v, set_i, ovp, ocp, actual_v, actual_i):
        return "programming/readback/measured output became invalid while output was ON"
    assert (set_v is not None and set_i is not None and ovp is not None
            and ocp is not None and actual_v is not None and actual_i is not None)

    tol = readback_tolerance
    if set_v > recipe_ceiling_v + tol:
        return f"set voltage {set_v:.3f}V exceeds recipe ceiling {recipe_ceiling_v:.3f}V"
    if set_v > absolute_voltage_ceiling_v + tol:
        return f"set voltage {set_v:.3f}V exceeds absolute ceiling"
    if actual_v > recipe_ceiling_v + tol:
        return f"measured output voltage {actual_v:.3f}V exceeds recipe ceiling {recipe_ceiling_v:.3f}V"
    if actual_v > absolute_voltage_ceiling_v + tol:
        return f"measured output voltage {actual_v:.3f}V exceeds absolute ceiling"
    # Zero disables OVP in RD60xx, rather than setting a zero-volt ceiling.
    if ovp > 0 and actual_v > ovp + tol:
        return f"measured output voltage {actual_v:.3f}V exceeds configured OVP {ovp:.3f}V"
    if set_i <= 0 or set_i > max_stage_current_a + tol:
        return f"set current {set_i:.3f}A exceeds runtime envelope"
    if actual_i > absolute_current_ceiling_a + tol:
        return f"measured current {actual_i:.3f}A exceeds absolute working-current envelope"
    if ocp > 0 and actual_i > ocp + tol:
        return f"measured current {actual_i:.3f}A exceeds configured OCP {ocp:.3f}A"
    if ovp > absolute_ovp_ceiling_v + tol:
        return f"OVP {ovp:.3f}V exceeds absolute protection ceiling"
    if ocp > absolute_ocp_ceiling_a + tol:
        return f"OCP {ocp:.3f}A exceeds absolute protection ceiling"
    if ovp > 0 and ovp + tol < set_v + protection_margin:
        return f"OVP {ovp:.3f}V does not protect set voltage {set_v:.3f}V"
    if ocp > 0 and ocp + tol < set_i + protection_margin:
        return f"OCP {ocp:.3f}A does not protect set current {set_i:.3f}A"
    return None
