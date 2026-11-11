"""Pure eligibility for bounded managed telemetry recovery.

This policy does not own the recovery clock, actuator commands or a watchdog.
Missing physical Output/protection truth never qualifies as an isolated
callback delay; confirmed hardware trips retain immediate safety authority.
"""
from __future__ import annotations

from typing import Any, Mapping

from rd6018_telemetry import (
    ProtectionStatus, finite_float, resolve_protection, telemetry_freshness,
)


def known_unsafe_observation(
    live: Mapping[str, Any], *,
    max_voltage_v: float,
    max_current_a: float,
    critical_battery_temp_c: float,
    max_psu_temp_c: float,
) -> bool:
    """Observed trip or limit violation preempts every telemetry wait."""
    if resolve_protection(live).status in {
        ProtectionStatus.OVP, ProtectionStatus.OCP, ProtectionStatus.OPP,
    }:
        return True
    for key, limit in (
        ("voltage", max_voltage_v),
        ("current", max_current_a),
        ("temp_ext", critical_battery_temp_c),
        ("temp_int", max_psu_temp_c),
    ):
        value = finite_float(live.get(key))
        if value is not None and value >= limit:
            return True
    return False


def isolated_callback_recovery_eligible(
    live: Mapping[str, Any],
    reason: str,
    *,
    output_known: bool,
    max_voltage_v: float,
    max_current_a: float,
    critical_battery_temp_c: float,
    max_psu_temp_c: float,
) -> bool:
    """Allow a 300s *wait*, not authorization to use a stale command readback."""
    if not output_known or not isinstance(live.get("_meta"), Mapping):
        return False
    if resolve_protection(live).status is not ProtectionStatus.NORMAL:
        return False
    if known_unsafe_observation(
        live, max_voltage_v=max_voltage_v, max_current_a=max_current_a,
        critical_battery_temp_c=critical_battery_temp_c,
        max_psu_temp_c=max_psu_temp_c,
    ):
        return False
    protect_keys = (
        ("protection_code",)
        if live.get("protection_code") not in (None, "", "unknown", "unavailable")
        else ("ovp_triggered", "ocp_triggered")
    )
    if not telemetry_freshness(live, ("switch",) + protect_keys).valid:
        return False
    text = str(reason or "").lower()
    if text.startswith("authoritative ") and "readback v2 is missing/stale" in text:
        return True
    if text.startswith("critical runtime telemetry is stale/incoherent: "):
        detail = text.split(": ", 1)[1]
        # Timestamp skew after a switch is a transient callback-batch mismatch.
        # Only accept it with a currently fresh Output/protection heartbeat.
        if detail.startswith("critical telemetry skew="):
            return True
        if " stale age=" in detail:
            key = detail.split(" stale age=", 1)[0]
            return key not in {"switch", "protection_code", "ovp_triggered", "ocp_triggered"}
    return False
