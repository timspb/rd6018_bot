from __future__ import annotations

from dataclasses import dataclass

from runtime.output.bridge import HardwareSnapshot


@dataclass(frozen=True)
class PhysicalSnapshotComparison:
    status: str
    fields: tuple[str, ...] = ()
    reason: str = ""


class PhysicalSnapshotComparator:
    @staticmethod
    def compare(left: HardwareSnapshot | None, right: HardwareSnapshot | None, tolerance: float = 0.06):
        if left is None or right is None:
            return PhysicalSnapshotComparison("INCONCLUSIVE", reason="snapshot_missing")
        fields = []
        for name in ("output_state", "measured_voltage", "measured_current", "configured_voltage", "configured_current", "ovp", "ocp"):
            a, b = getattr(left, name), getattr(right, name)
            if a is None or b is None:
                continue
            if (isinstance(a, bool) and a != b) or (isinstance(a, (int, float)) and abs(a - b) > tolerance):
                fields.append(name)
        return PhysicalSnapshotComparison("MATCH" if not fields else "MISMATCH", tuple(fields), "equal" if not fields else "fields_differ")
