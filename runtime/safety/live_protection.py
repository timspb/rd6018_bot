"""Pure policy for live RD6018 protection observations.

This module never writes hardware and never decides charge chemistry.
The production dispatcher keeps journal/notification/OFF side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LiveProtectionDecision:
    """Ordered confirmed trips and the normalized evidence used."""

    triggers: tuple[str, ...]
    evidence: tuple[tuple[str, object], ...]

    @property
    def shutdown_required(self) -> bool:
        return bool(self.triggers)


def evaluate_live_protection(
    *,
    charge_active: bool,
    output_on: bool,
    ovp_triggered: Optional[bool],
    ocp_triggered: Optional[bool],
    internal_temperature_c: Optional[float],
    precritical_temperature_c: float,
) -> LiveProtectionDecision:
    """Return live protection evidence in original production dispatch order.

    Unknown or absent indicators do not constitute a confirmed fault. Other
    production/electrical containment authorities remain independent.
    """
    triggers: list[str] = []
    evidence: list[tuple[str, object]] = []
    if charge_active and ovp_triggered is True:
        triggers.append("OVP_TRIGGERED")
        evidence.append(("ovp_triggered", True))
    if charge_active and ocp_triggered is True:
        triggers.append("OCP_TRIGGERED")
        evidence.append(("ocp_triggered", True))
    if (
        (output_on or charge_active)
        and internal_temperature_c is not None
        and internal_temperature_c >= precritical_temperature_c
    ):
        triggers.append("TEMP_INT_PRECRITICAL")
        evidence.append(("internal_temperature_c", internal_temperature_c))
    return LiveProtectionDecision(tuple(triggers), tuple(evidence))


__all__ = ["LiveProtectionDecision", "evaluate_live_protection"]
