from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config import MAX_VOLTAGE


@dataclass(frozen=True)
class LegacySafetyDecision:
    stop: bool
    reason: str = ""


def clamp_legacy_target_voltage(voltage_v: float) -> float:
    """Clamp legacy profile targets after all compensation.

    Expert V2 recipes intentionally do not use this helper; their explicit recipe
    envelope is enforced by SafetySupervisor/SafeOutputCoordinator instead.
    """
    return round(min(float(MAX_VOLTAGE), max(0.0, float(voltage_v))), 2)


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
    normalized = str(profile).strip().upper()
    if normalized == "EFB":
        return 20.0
    if normalized in {"CA/CA", "CA"}:
        return 20.0
    if normalized == "AGM":
        return 10.0
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
