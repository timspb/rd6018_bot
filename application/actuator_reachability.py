"""Static actuator reachability inventory for the preserved V2 runtime."""

from __future__ import annotations

from dataclasses import dataclass

from .actuator_intent_mapping import known_actuator_paths


@dataclass(frozen=True)
class ActuatorReachabilityRecord:
    path_id: str
    operation: str
    source: str
    caller: str
    owner: str
    adapter: str
    physical_target: str
    migration_status: str
    production_reachable: bool
    dispatch_enabled: bool = False


def actuator_reachability() -> tuple[ActuatorReachabilityRecord, ...]:
    records = [
        ActuatorReachabilityRecord(
            path.path_id, path.current_operation.value.upper(), path.caller, path.caller,
            path.owner, "V2 compatibility / SafeOutput boundary", path.target,
            "KEEP_COMPATIBILITY" if path.classification == "KEEP" else "DEPRECATE",
            True, False,
        )
        for path in known_actuator_paths()
    ]
    records.extend((
        ActuatorReachabilityRecord("controller-start", "START", "ChargeController", "ChargeController.start", "V2 controller", "V2 transaction boundary", "RD6018 Output", "KEEP_COMPATIBILITY", True, False),
        ActuatorReachabilityRecord("controller-stop", "STOP", "ChargeController", "ChargeController.stop", "V2 controller", "SafeOutputCoordinator", "RD6018 Output", "KEEP_COMPATIBILITY", True, False),
        ActuatorReachabilityRecord("emergency-stop", "EMERGENCY_OFF", "runtime safety", "emergency stop path", "V2 safety", "SafeOutputCoordinator / edge dead-man", "RD6018 Output", "KEEP_COMPATIBILITY", True, False),
        ActuatorReachabilityRecord("containment", "CONTAINMENT", "safety boundary", "containment request", "Safety Decision Authority", "Execution Boundary (shadow only)", "RD6018 Output", "SHADOW_ONLY", False, False),
    ))
    return tuple(records)


def actuator_bypasses() -> tuple[ActuatorReachabilityRecord, ...]:
    """Return legacy production paths not yet routed through V3 dispatcher."""
    return tuple(record for record in actuator_reachability() if record.production_reachable and record.dispatch_enabled is False)


__all__ = ["ActuatorReachabilityRecord", "actuator_reachability", "actuator_bypasses"]
