from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any, Mapping

from runtime.output.bridge import HardwareSnapshot

from .models import PhysicalCommandTarget
from .target import validate_target


_READBACK_FIELDS = {
    "voltage_setpoint": "configured_voltage",
    "current_setpoint": "configured_current",
    "ovp": "ovp",
    "ocp": "ocp",
    "output_state": "output_state",
    "current": "measured_current",
    "voltage": "measured_voltage",
    "temperature": "temperature",
}


@dataclass(frozen=True)
class CommandVerificationResult:
    connector: str
    result: str
    differences: tuple[str, ...]
    before_snapshot: HardwareSnapshot | None
    after_snapshot: HardwareSnapshot | None


@dataclass(frozen=True)
class DualCommandVerification:
    target: PhysicalCommandTarget
    results: tuple[CommandVerificationResult, ...]
    comparison: str


def verify_target(target: PhysicalCommandTarget, after: HardwareSnapshot | None, *, connector: str,
                  now: float | None = None, max_age: float = 10.0,
                  before: HardwareSnapshot | None = None) -> CommandVerificationResult:
    validation = validate_target(target)
    if not validation.valid:
        return CommandVerificationResult(connector, "FAILED", (validation.reason,), before, after)
    if after is None:
        return CommandVerificationResult(connector, "FAILED", ("snapshot_missing",), before, after)
    differences: list[str] = []
    current_time = time() if now is None else now
    if current_time - after.timestamp > max_age:
        differences.append("timestamp_stale")
    for field, expected in target.expected_readback.items():
        snapshot_field = _READBACK_FIELDS.get(field, field)
        actual = getattr(after, snapshot_field, None)
        if actual is None:
            differences.append(f"missing:{field}")
        elif isinstance(expected, bool):
            if actual != expected:
                differences.append(field)
        elif abs(float(actual) - float(expected)) > target.tolerance[field]:
            differences.append(field)
    return CommandVerificationResult(connector, "MATCH" if not differences else "MISMATCH",
                                     tuple(differences), before, after)


def compare_dual(target: PhysicalCommandTarget, results: tuple[CommandVerificationResult, ...]) -> DualCommandVerification:
    statuses = {result.result for result in results}
    comparison = "MATCH" if len(results) == 2 and statuses == {"MATCH"} else "MISMATCH"
    return DualCommandVerification(target, results, comparison)
