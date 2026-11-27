"""Pure chemistry and prior-age admission for adopted high-voltage Mix."""

from __future__ import annotations

import math
from typing import Any

from pb_domain import BatteryChemistry
from rd_live_adoption import MIX_HARD_LIMIT_HOURS
from recipe_engine import POLICIES
from runtime.safety.runtime_guard import RuntimeSafetyError


def _finite_nonnegative(value: Any, *, field: str) -> float:
    if value is None or isinstance(value, bool):
        raise RuntimeSafetyError(f"{field} is required")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeSafetyError(f"{field} is invalid") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise RuntimeSafetyError(f"{field} is invalid")
    return parsed


def require_adopted_mix_chemistry(
    chemistry: BatteryChemistry,
    capacity_ah: float,
    fingerprint: Any,
    *,
    absolute_current_ceiling_a: float,
    tolerance: float,
) -> None:
    """Raise the established D062 safety error unless an existing Mix fits its envelope."""
    if chemistry not in MIX_HARD_LIMIT_HOURS or chemistry is BatteryChemistry.CUSTOM:
        raise RuntimeSafetyError("MIX_ADOPTED requires a supported Pb chemistry")
    capacity = _finite_nonnegative(capacity_ah, field="battery capacity")
    if capacity <= 0:
        raise RuntimeSafetyError("MIX_ADOPTED requires positive battery capacity")
    policy = POLICIES[chemistry]
    tol = float(tolerance)
    if fingerprint.set_voltage_v <= policy.normal_voltage_ceiling_v + tol:
        raise RuntimeSafetyError("MIX_ADOPTED requires an already-running high-voltage Mix program")
    if fingerprint.set_voltage_v > policy.recovery_voltage_ceiling_v + tol:
        raise RuntimeSafetyError(
            f"live Mix voltage {fingerprint.set_voltage_v:.2f}V exceeds {chemistry.value} envelope "
            f"{policy.recovery_voltage_ceiling_v:.2f}V"
        )
    hv_current_limit = min(
        float(absolute_current_ceiling_a),
        capacity * float(policy.hv_current_c_max),
    )
    if fingerprint.set_current_a > hv_current_limit + tol:
        raise RuntimeSafetyError(
            f"live Mix current {fingerprint.set_current_a:.2f}A exceeds chemistry HV envelope "
            f"{hv_current_limit:.2f}A"
        )


def require_adopted_mix_budget(chemistry: BatteryChemistry, prior_elapsed_s: float) -> None:
    """Raise the established D062 error when prior active age reaches the hard limit."""
    limit_h = MIX_HARD_LIMIT_HOURS.get(chemistry)
    if limit_h is None:
        raise RuntimeSafetyError("MIX_ADOPTED chemistry has no hard Mix limit")
    if float(prior_elapsed_s) >= float(limit_h) * 3600.0:
        raise RuntimeSafetyError(
            f"prior Mix age {float(prior_elapsed_s) / 3600.0:.2f}h already exhausts "
            f"{chemistry.value} hard limit {limit_h:g}h; managed Mix adoption is forbidden"
        )
