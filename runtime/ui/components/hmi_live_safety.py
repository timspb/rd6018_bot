"""Read-only live safety labels and canonical telemetry freshness."""

from __future__ import annotations
from typing import Any, Mapping
from rd6018_telemetry import telemetry_freshness
from .hmi_values import _on

def _normal_safety(live: Mapping[str, Any]) -> tuple[str, str]:
    tripped = []
    if _on(live.get("ovp_triggered")):
        tripped.append("OVP")
    if _on(live.get("ocp_triggered")):
        tripped.append("OCP")
    if tripped:
        return "⚠️ Защита: " + "/".join(tripped), "alarm"
    return "Защита: норма", "normal"


def _operator_telemetry_fresh(live: Mapping[str, Any]) -> bool:
    """Use the bounded freshness contract for truthful presentation."""

    return telemetry_freshness(
        live,
        ("switch", "battery_voltage", "current", "protection_code", "regulation_code"),
    ).valid
