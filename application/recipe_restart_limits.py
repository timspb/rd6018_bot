"""Reuse production START offsets with an existing charge-session voltage ceiling."""
from __future__ import annotations
import math
from typing import Any


def existing_start_limits(host: Any, *, voltage_v: float, current_a: float,
                          voltage_ceiling_v: float) -> tuple[float, float, float]:
    """Use START's OVP/OCP offsets; ceiling must come from the active session envelope."""
    values = (voltage_v, current_a, voltage_ceiling_v,
              host.OVP_OFFSET, host.OCP_OFFSET)
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) for v in values):
        raise ValueError("invalid existing START limits")
    voltage_v, current_a, ceiling, ovp_offset, ocp_offset = map(float, values)
    if not (0 < voltage_v <= ceiling and current_a > 0
            and ovp_offset > 0 and ocp_offset > 0):
        raise ValueError("recipe target exceeds existing session envelope")
    limited_current = float(host._cap_current(current_a))
    if not math.isfinite(limited_current) or limited_current <= 0:
        raise ValueError("existing current cap rejects recipe target")
    if limited_current < current_a:
        raise ValueError("recipe target exceeds existing current cap")
    return (voltage_v + ovp_offset, current_a + ocp_offset, ceiling)
