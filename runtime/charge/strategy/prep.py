"""Pure automatic PREP / soft-start target selection."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.charge.strategy.prep_variables import (
    PREP_CURRENT_C_RATE,
    PREP_MIN_CURRENT_A,
    PREP_VOLTAGE_V,
)


@dataclass(frozen=True)
class PrepTarget:
    voltage_v: float
    current_a: float


def select_prep_target(*, capacity_ah: float) -> PrepTarget:
    # Lazy import avoids runtime.safety package initialization cycles.
    from runtime.safety.variables import MAX_STAGE_CURRENT_A

    capacity = max(1.0, float(capacity_ah))
    current = max(
        float(PREP_MIN_CURRENT_A.default),
        capacity * float(PREP_CURRENT_C_RATE.default),
    )
    current = min(current, float(MAX_STAGE_CURRENT_A.default))
    return PrepTarget(
        voltage_v=float(PREP_VOLTAGE_V.default),
        current_a=current,
    )


__all__ = ["PrepTarget", "select_prep_target"]
