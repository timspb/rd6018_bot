from __future__ import annotations

from time import time
from typing import Any

from runtime.output.bridge import HardwareSnapshot

from .models import VerificationResult


class PhysicalStateComparator:
    """Fail-closed comparison of one expected and one physical snapshot."""

    def __init__(self, *, voltage_tolerance: float, current_tolerance: float,
                 protection_tolerance: float, timestamp_tolerance: float, clock=time):
        self.voltage_tolerance = voltage_tolerance
        self.current_tolerance = current_tolerance
        self.protection_tolerance = protection_tolerance
        self.timestamp_tolerance = timestamp_tolerance
        self.clock = clock

    def compare(self, expected: HardwareSnapshot | None, observed: HardwareSnapshot | None,
                *, require_fields: tuple[str, ...] = (), now: float | None = None) -> tuple[str, tuple[str, ...]]:
        if expected is None or observed is None:
            return VerificationResult.FAILED, ("snapshot_missing",)
        differences: list[str] = []
        current_time = self.clock() if now is None else now
        if current_time - observed.timestamp > self.timestamp_tolerance:
            differences.append("timestamp_stale")
        for name in require_fields:
            if getattr(observed, name, None) is None:
                differences.append(f"missing:{name}")
        fields = set(require_fields)
        for name in ("output_state", "measured_voltage", "measured_current", "configured_voltage",
                     "configured_current", "ovp", "ocp", "temperature"):
            expected_value = getattr(expected, name, None)
            observed_value = getattr(observed, name, None)
            if expected_value is None:
                continue
            if observed_value is None:
                if name not in fields:
                    differences.append(f"missing:{name}")
                continue
            if isinstance(expected_value, bool):
                if expected_value != observed_value:
                    differences.append(name)
                continue
            tolerance = self.current_tolerance if "current" in name else self.protection_tolerance if name in {"ovp", "ocp"} else self.voltage_tolerance if "voltage" in name else 0.0
            if abs(float(expected_value) - float(observed_value)) > tolerance:
                differences.append(name)
        return (VerificationResult.MATCH if not differences else VerificationResult.MISMATCH), tuple(differences)
