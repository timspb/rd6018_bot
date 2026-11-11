"""Ownership-neutral safety policy for foreign Output ON detection."""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from rd6018_telemetry import ProtectionStatus, finite_float, resolve_protection, telemetry_freshness

def foreign_output_safety_error(live: Mapping[str, Any], *, max_internal_temp_c: float) -> str | None:
    """No Pb recipe or session policy may seize foreign Output ownership."""
    if not isinstance(live.get("_meta"), dict):
        return "unmanaged Output ON lacks freshness metadata for ownership recovery"
    protection_code = live.get("protection_code")
    if protection_code not in (None, "", "unknown", "unavailable"):
        protection_keys = ("protection_code",)
    else:
        protection_keys = ("ovp_triggered", "ocp_triggered")
    freshness = telemetry_freshness(live, ("switch",) + protection_keys)
    if not freshness.valid:
        return ("unmanaged Output ON has stale/incoherent ownership-neutral telemetry: "
                f"{freshness.detail}")
    protection = resolve_protection(live)
    if protection.status is ProtectionStatus.UNKNOWN:
        return "RD6018 protection status is unknown during ownership recovery"
    if protection.tripped:
        return f"RD6018 {protection.status.value.upper()} protection is tripped"
    temp_int = finite_float(live.get("temp_int"))
    if temp_int is not None and temp_int >= max_internal_temp_c:
        return f"RD6018 temperature {temp_int:.1f}C >= {max_internal_temp_c:.1f}C"
    return None
