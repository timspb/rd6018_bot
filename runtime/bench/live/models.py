from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.output.bridge import HardwareSnapshot
from runtime.physical.transports.comparator import PhysicalSnapshotComparison


@dataclass(frozen=True)
class LiveSnapshotRun:
    timestamp: float
    transport: str
    device: str
    snapshot: HardwareSnapshot | None
    quality: str
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class PhysicalSnapshotEvidence:
    timestamp: float
    operator: str
    ha_snapshot: HardwareSnapshot | None
    esp_snapshot: HardwareSnapshot | None
    comparison: PhysicalSnapshotComparison
    runs: tuple[LiveSnapshotRun, ...] = ()

