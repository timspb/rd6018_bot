"""Read-only hardware snapshots and readback validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HardwareSnapshot:
    timestamp: float
    connection_state: str
    output_state: bool | None = None
    measured_voltage: float | None = None
    measured_current: float | None = None
    configured_voltage: float | None = None
    configured_current: float | None = None
    ovp: float | None = None
    ocp: float | None = None
    temperature: float | None = None
    battery_voltage: float | None = None


@dataclass(frozen=True)
class ReadbackValidation:
    valid: bool
    mismatches: tuple[str, ...] = ()


def validate_readback(snapshot: HardwareSnapshot, *, expected_output: bool | None = None, tolerance: float = 0.06) -> ReadbackValidation:
    mismatches: list[str] = []
    if not snapshot.connection_state.strip():
        mismatches.append("connection_state")
    if expected_output is not None and snapshot.output_state != expected_output:
        mismatches.append("output_state")
    if snapshot.configured_voltage is not None and snapshot.measured_voltage is not None and abs(snapshot.configured_voltage - snapshot.measured_voltage) > tolerance:
        mismatches.append("voltage")
    if snapshot.configured_current is not None and snapshot.measured_current is not None and abs(snapshot.configured_current - snapshot.measured_current) > tolerance:
        mismatches.append("current")
    return ReadbackValidation(not mismatches, tuple(mismatches))
