"""Canonical, non-executing actuator ownership inventory for Workstream 3."""

from __future__ import annotations

from dataclasses import dataclass

from .actuator_reachability import actuator_reachability


@dataclass(frozen=True)
class CanonicalActuatorPath:
    operation: str
    owner: str
    source: str
    path: str
    adapter: str
    physical_target: str
    migration_state: str


_EXPLICIT_PATHS = (
    CanonicalActuatorPath("OUTPUT_ON", "V2 transaction owner", "runtime/v2_runtime.py", "hass.turn_on", "V2/SafeOutput compatibility", "RD6018 Output", "KEEP"),
    CanonicalActuatorPath("OUTPUT_OFF", "V2 safety owner", "runtime/v2_runtime.py", "hass.turn_off", "V2/SafeOutput compatibility", "RD6018 Output", "KEEP"),
    CanonicalActuatorPath("SET_VOLTAGE", "V2 transaction owner", "runtime/v2_runtime.py", "hass.set_voltage", "V2/SafeOutput compatibility", "RD6018 voltage", "KEEP"),
    CanonicalActuatorPath("SET_CURRENT", "V2 transaction owner", "runtime/v2_runtime.py", "hass.set_current", "V2/SafeOutput compatibility", "RD6018 current", "KEEP"),
    CanonicalActuatorPath("OUTPUT_OFF", "SafeOutputCoordinator", "safe_output.py", "_ensure_output_off", "SafeOutput", "RD6018 Output", "KEEP"),
    CanonicalActuatorPath("OUTPUT_OFF", "Runtime Safety", "runtime_safety.py", "_ensure_output_off", "SafeOutput/RD boundary", "RD6018 Output", "KEEP"),
    CanonicalActuatorPath("OUTPUT_OFF", "Runtime Safety V2", "runtime_safety_v2.py", "_ensure_output_off", "SafeOutput/RD boundary", "RD6018 Output", "KEEP"),
    CanonicalActuatorPath("OUTPUT_OFF", "Strict Runtime Safety", "runtime_safety_strict.py", "_ensure_output_off", "SafeOutput/RD boundary", "RD6018 Output", "KEEP"),
    CanonicalActuatorPath("OUTPUT_OFF", "Manual Runtime", "manual_runtime_v2.py", "_contain_enable_exception/stop", "V2 manual compatibility", "RD6018 Output", "KEEP"),
    CanonicalActuatorPath("OUTPUT_OFF", "Diagnostic Probe", "diagnostic_probe.py", "_restore_or_off", "Diagnostic compatibility", "RD6018 Output", "DEPRECATE"),
    CanonicalActuatorPath("SET_VOLTAGE", "Diagnostic Probe", "diagnostic_probe.py", "probe", "Diagnostic compatibility", "RD6018 voltage", "DEPRECATE"),
    CanonicalActuatorPath("SET_CURRENT", "Diagnostic Probe", "diagnostic_probe.py", "probe", "Diagnostic compatibility", "RD6018 current", "DEPRECATE"),
    CanonicalActuatorPath("OUTPUT_OFF", "Edge Safety Lease", "edge_safety_lease.py", "expiry/dead-man", "ESPHome/edge lease", "RD6018 Output", "KEEP"),
    CanonicalActuatorPath("OUTPUT_ON", "ESP Direct transport", "runtime/physical/connectors/esp_direct.py", "output_on", "RD transport adapter", "RD6018 Output", "ADAPTER"),
    CanonicalActuatorPath("OUTPUT_OFF", "ESP Direct transport", "runtime/physical/connectors/esp_direct.py", "output_off", "RD transport adapter", "RD6018 Output", "ADAPTER"),
    CanonicalActuatorPath("SET_VOLTAGE", "ESP Direct transport", "runtime/physical/connectors/esp_direct.py", "set_voltage", "RD transport adapter", "RD6018 voltage", "ADAPTER"),
    CanonicalActuatorPath("SET_CURRENT", "ESP Direct transport", "runtime/physical/connectors/esp_direct.py", "set_current", "RD transport adapter", "RD6018 current", "ADAPTER"),
)


def canonical_actuator_paths() -> tuple[CanonicalActuatorPath, ...]:
    """Return the union of normalized known paths and explicit direct paths."""
    normalized = tuple(
        CanonicalActuatorPath(
            path.operation, path.owner, path.source, path.caller,
            path.adapter, path.physical_target, "KEEP" if path.migration_status == "KEEP_COMPATIBILITY" else "DEPRECATE",
        )
        for path in actuator_reachability()
    )
    return normalized + _EXPLICIT_PATHS


def direct_bypasses() -> tuple[CanonicalActuatorPath, ...]:
    return tuple(path for path in canonical_actuator_paths() if path.migration_state in {"KEEP", "DEPRECATE"} and "Dispatcher" not in path.adapter)


__all__ = ["CanonicalActuatorPath", "canonical_actuator_paths", "direct_bypasses"]
