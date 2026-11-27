"""Independent live OPP and internal-temperature trip policy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from rd6018_telemetry import ProtectionStatus, resolve_protection


@dataclass(frozen=True)
class LiveProtectionDecision:
    triggers: tuple[str, ...]
    evidence: tuple[tuple[str, object], ...]

    @property
    def shutdown_required(self) -> bool:
        return bool(self.triggers)


def evaluate_live_protection(
    *,
    live: Mapping[str, Any],
    charge_active: bool,
    output_on: bool,
    internal_temperature_c: Optional[float],
    precritical_temperature_c: float,
) -> LiveProtectionDecision:
    triggers: list[str] = []
    evidence: list[tuple[str, object]] = []
    protection = resolve_protection(live)
    if charge_active and protection.status is ProtectionStatus.OPP:
        triggers.append("OPP_TRIGGERED")
        evidence.append(("hardware_protection", "OPP"))
    if ((output_on or charge_active) and internal_temperature_c is not None
            and internal_temperature_c >= precritical_temperature_c):
        triggers.append("TEMP_INT_PRECRITICAL")
        evidence.append(("internal_temperature_c", internal_temperature_c))
    return LiveProtectionDecision(tuple(triggers), tuple(evidence))


__all__ = ["LiveProtectionDecision", "evaluate_live_protection"]
