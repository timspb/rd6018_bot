"""Compatibility inventory for preserved V2 actuator paths.

This registry does not redirect or execute a physical call. It makes every
legacy path explicit before any future adapter migration.
"""

from __future__ import annotations

from dataclasses import dataclass

from .actuator_intent import ActuatorOperation
from .actuator_intent_mapping import known_actuator_paths


@dataclass(frozen=True)
class LegacyActuatorCompatibilityPath:
    path_id: str
    operation: ActuatorOperation
    source: str
    current_owner: str
    adapter_boundary: str
    dispatch_enabled: bool = False


def legacy_actuator_compatibility_paths() -> tuple[LegacyActuatorCompatibilityPath, ...]:
    return tuple(
        LegacyActuatorCompatibilityPath(
            path.path_id, path.current_operation, path.caller, path.owner,
            "V2 compatibility / SafeOutput boundary", False,
        )
        for path in known_actuator_paths()
    )


__all__ = ["LegacyActuatorCompatibilityPath", "legacy_actuator_compatibility_paths"]
