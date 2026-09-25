from __future__ import annotations

from runtime.physical.transports import PhysicalSnapshotComparator, PhysicalSnapshotComparison


class ConnectorSnapshotComparator:
    @staticmethod
    def compare(left, right, *, voltage_tolerance=0.06, current_tolerance=0.06,
                timestamp_tolerance=10.0) -> PhysicalSnapshotComparison:
        return PhysicalSnapshotComparator.compare(
            left, right, tolerance=voltage_tolerance,
            current_tolerance=current_tolerance,
            timestamp_tolerance=timestamp_tolerance,
        )
