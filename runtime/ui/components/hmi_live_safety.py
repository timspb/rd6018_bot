"""Read-only live safety labels and canonical telemetry freshness."""

from __future__ import annotations
from typing import Any, Mapping
from rd6018_telemetry import telemetry_freshness
from runtime.safety.protection_boundary import ProtectionVerdict, assess_protection
from .hmi_values import _on

def _normal_safety(live: Mapping[str, Any]) -> tuple[str, str]:
    protection = assess_protection(live)
    if protection.verdict is ProtectionVerdict.TRIPPED:
        return "⚠️ Защита сработала", "alarm"
    if protection.verdict is ProtectionVerdict.UNKNOWN:
        return "⚠️ Защита не подтверждена", "warning"
    return "Защита: норма", "normal"


def _protection_tripped(live: Mapping[str, Any]) -> bool:
    return assess_protection(live).verdict is ProtectionVerdict.TRIPPED


def _operator_telemetry_fresh(live: Mapping[str, Any]) -> bool:
    """Use the bounded freshness contract for truthful presentation."""

    return telemetry_freshness(
        live,
        ("switch", "battery_voltage", "current", "regulation_code"),
    ).valid
