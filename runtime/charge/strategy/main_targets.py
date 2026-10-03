"""Pure MAIN target selection.

Returns base voltage/current before temperature compensation and execution
envelope checks. No controller, transport or persistence dependency is allowed.
"""

from __future__ import annotations

from dataclasses import dataclass

from runtime.safety.variables import MAX_STAGE_CURRENT_A

from .main_variables import (
    AGM_STAGE_VOLTAGES_V,
    CA_MAIN_VOLTAGE_V,
    DEFAULT_MAIN_VOLTAGE_V,
    EFB_MAIN_VOLTAGE_V,
    MAIN_CURRENT_C_RATE,
)


@dataclass(frozen=True)
class MainTarget:
    voltage_v: float
    current_a: float


def select_main_target(
    *,
    profile: str,
    capacity_ah: float,
    agm_stage_idx: int = 0,
    current_ceiling_a: float | None = None,
) -> MainTarget:
    """Return the accepted MAIN base target for one battery profile."""
    capacity = max(1.0, float(capacity_ah))
    ceiling = (
        float(MAX_STAGE_CURRENT_A.default)
        if current_ceiling_a is None
        else max(0.1, float(current_ceiling_a))
    )
    current = min(
        ceiling,
        capacity * float(MAIN_CURRENT_C_RATE.default),
    )

    profile_upper = str(profile).strip().upper()
    if profile_upper in {"CA/CA", "CA"}:
        voltage = float(CA_MAIN_VOLTAGE_V.default)
    elif profile_upper == "EFB":
        voltage = float(EFB_MAIN_VOLTAGE_V.default)
    elif profile_upper == "AGM":
        stages = tuple(float(value) for value in AGM_STAGE_VOLTAGES_V.default)
        idx = min(max(0, int(agm_stage_idx)), len(stages) - 1)
        voltage = stages[idx]
    else:
        voltage = float(DEFAULT_MAIN_VOLTAGE_V.default)

    return MainTarget(voltage_v=voltage, current_a=current)


__all__ = ["MainTarget", "select_main_target"]
