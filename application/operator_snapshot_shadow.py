"""Read-only parity comparison between legacy HMI and V3 snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .operator_snapshot import OperatorSnapshot


@dataclass(frozen=True)
class OperatorSnapshotParity:
    status: str
    matched_fields: tuple[str, ...]
    mismatches: tuple[str, ...]


def compare_hmi_to_snapshot(legacy: Any, current: OperatorSnapshot) -> OperatorSnapshotParity:
    process = getattr(getattr(legacy, "process_state", None), "value", getattr(legacy, "process_state", ""))
    legacy_active = process in {"running", "paused", "storage", "adopted_mix"}
    expected_state = "CHARGING" if legacy_active else ("FAULT" if process in {"containment", "hands_off", "interrupted"} else "IDLE")
    actual = current.snapshot
    checks = {
        "process_state": expected_state == current.state,
        "voltage": getattr(legacy, "battery_voltage_v", None) == actual.telemetry.voltage,
        "current": getattr(legacy, "current_a", None) == actual.telemetry.current,
        "power": getattr(legacy, "power_w", None) == actual.output.get("power_w"),
        "safety": bool(getattr(legacy, "attention", "normal") != "alarm") == actual.safety.allowed,
        "fault_state": bool(getattr(legacy, "attention", "normal") == "alarm") == bool(current.faults),
    }
    matched = tuple(name for name, ok in checks.items() if ok)
    mismatches = tuple(name for name, ok in checks.items() if not ok)
    return OperatorSnapshotParity("MATCH" if not mismatches else "MISMATCH", matched, mismatches)
