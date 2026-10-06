"""Production Cooling continuation validation.

This module validates durable Cooling resume authority.  It is deliberately pure:
no controller monkey-patching, persistence writes, hardware writes, or transition
execution live here.
"""

from __future__ import annotations

import math
from typing import Any, Tuple

from config import MAX_MANUAL_VOLTAGE
from runtime.safety.variables import MAX_STAGE_CURRENT_A


def finite(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def validate_cooling_pause(controller: Any, pause: Any) -> Tuple[bool, str]:
    """Validate durable Cooling continuation authority before automatic resume."""
    if not isinstance(pause, dict):
        return False, "v2_cooling_pause_missing"

    source_stage = str(pause.get("source_stage") or "")
    allowed_sources = {
        controller.STAGE_PREP,
        controller.STAGE_MAIN,
        controller.STAGE_DESULFATION,
        controller.STAGE_MIX,
        controller.STAGE_SAFE_WAIT,
    }
    if source_stage not in allowed_sources:
        return False, "cooling_source_stage_invalid"

    entered_at = finite(pause.get("entered_at"))
    source_stage_start = finite(pause.get("source_stage_start_time"))
    if entered_at is None or entered_at <= 0:
        return False, "cooling_entered_at_invalid"
    if source_stage_start is None or source_stage_start <= 0:
        return False, "cooling_source_stage_clock_invalid"

    if source_stage == controller.STAGE_SAFE_WAIT:
        safe_wait_start = finite(pause.get("source_safe_wait_start"))
        safe_wait_v = finite(getattr(controller, "_safe_wait_target_v", None))
        safe_wait_i = finite(getattr(controller, "_safe_wait_target_i", None))
        next_stage = getattr(controller, "_safe_wait_next_stage", None)
        if safe_wait_start is None or safe_wait_start <= 0:
            return False, "cooling_safe_wait_clock_missing"
        if (
            safe_wait_v is None
            or safe_wait_v <= 0
            or safe_wait_i is None
            or safe_wait_i <= 0
        ):
            return False, "cooling_safe_wait_target_missing"
        if next_stage not in {controller.STAGE_MAIN, controller.STAGE_DONE}:
            return False, "cooling_safe_wait_next_stage_invalid"
        return True, "ok"

    target_v = finite(pause.get("target_v"))
    target_i = finite(pause.get("target_i"))
    if target_v is None or target_v <= 0 or target_i is None or target_i <= 0:
        return False, "cooling_source_target_missing"
    if target_v > float(MAX_MANUAL_VOLTAGE) + 1e-9:
        return False, "cooling_source_voltage_over_absolute_ceiling"
    if target_i > float(MAX_STAGE_CURRENT_A.default) + 1e-9:
        return False, "cooling_source_current_over_absolute_ceiling"

    envelope_fn = getattr(controller, "_recipe_envelope", None)
    bound_fn = getattr(controller, "_bound_target", None)
    if callable(envelope_fn) and callable(bound_fn):
        try:
            envelope = envelope_fn()
            hv = source_stage in {controller.STAGE_DESULFATION, controller.STAGE_MIX}
            bounded_v, bounded_i = bound_fn((target_v, target_i), envelope, hv=hv)
        except Exception:
            return False, "cooling_source_target_could_not_be_reauthorized"
        if (
            abs(float(bounded_v) - target_v) > 1e-6
            or abs(float(bounded_i) - target_i) > 1e-6
        ):
            return False, "cooling_source_target_outside_current_recipe"

    return True, "ok"


__all__ = ["finite", "validate_cooling_pause"]
