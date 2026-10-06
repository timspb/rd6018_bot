from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from runtime.charge.strategy.mix_variables import (
    AGM_MIX_MAX_ACTIVE_HOURS,
    CA_MIX_MAX_ACTIVE_HOURS,
    EFB_MIX_MAX_ACTIVE_HOURS,
)
from runtime.safety.voltage_variables import clamp_pb_automatic_target_voltage


@dataclass(frozen=True)
class LegacySafetyDecision:
    stop: bool
    reason: str = ""


def clamp_legacy_target_voltage(voltage_v: float) -> float:
    """Clamp legacy profile targets after all compensation.

    Expert V2 recipes intentionally do not use this helper; their explicit recipe
    envelope is enforced by SafetySupervisor/SafeOutputCoordinator instead.
    """
    return clamp_pb_automatic_target_voltage(voltage_v)


def main_timeout_decision(
    *,
    elapsed_hours: float,
    max_hours: float,
) -> LegacySafetyDecision:
    """MAIN hard timeout is non-bypassable and never escalates voltage."""
    if float(elapsed_hours) < float(max_hours):
        return LegacySafetyDecision(False)
    return LegacySafetyDecision(
        True,
        f"MAIN hard safety timeout reached: {float(elapsed_hours):.2f}h >= {float(max_hours):.2f}h",
    )


def mix_timeout_hours(profile: str) -> Optional[float]:
    """Compatibility facade over canonical automatic MIX authority limits."""
    normalized = str(profile).strip().upper()
    if normalized == "EFB":
        return float(EFB_MIX_MAX_ACTIVE_HOURS.default)
    if normalized in {"CA/CA", "CA"}:
        return float(CA_MIX_MAX_ACTIVE_HOURS.default)
    if normalized == "AGM":
        return float(AGM_MIX_MAX_ACTIVE_HOURS.default)
    return None


def mix_timeout_decision(
    *,
    profile: str,
    elapsed_hours: float,
    finish_timer_active: bool = False,
) -> LegacySafetyDecision:
    """Profile Mix observation ceilings are fallback limits.

    Once a delta/reversal has been confirmed and its finish-hold timer is active,
    that confirmed event owns normal Mix completion. Thermal, telemetry and hardware
    safety remain independent and can still interrupt the hold.
    """
    if finish_timer_active:
        return LegacySafetyDecision(False)
    limit = mix_timeout_hours(profile)
    if limit is None or float(elapsed_hours) < limit:
        return LegacySafetyDecision(False)
    return LegacySafetyDecision(
        True,
        f"{profile} Mix fallback timeout reached: {float(elapsed_hours):.2f}h >= {limit:.2f}h",
    )
