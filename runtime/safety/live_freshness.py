"""Pure runtime telemetry freshness projection, without safety side effects."""
from __future__ import annotations
from typing import Any, Mapping
from rd6018_telemetry import telemetry_freshness


def runtime_freshness_error(
    live: Mapping[str, Any], *, output_state: bool | None,
    required_keys: tuple[str, ...],
) -> str | None:
    if not isinstance(live.get("_meta"), dict):
        return "critical runtime telemetry freshness metadata is missing"
    keys = list(required_keys)
    if output_state is True:
        keys.append("voltage")
    if live.get("protection_code") not in (None, "", "unknown", "unavailable"):
        keys.append("protection_code")
    else:
        keys.extend(("ovp_triggered", "ocp_triggered"))
    if output_state is True:
        if live.get("regulation_code") not in (None, "", "unknown", "unavailable"):
            keys.append("regulation_code")
        else:
            for key in ("is_cv", "is_cc"):
                if live.get(key) not in (None, "", "unknown", "unavailable"):
                    keys.append(key)
    freshness = telemetry_freshness(live, keys)
    if freshness.valid:
        return None
    return f"critical runtime telemetry is stale/incoherent: {freshness.detail}"
