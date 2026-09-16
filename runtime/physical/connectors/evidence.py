from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PhysicalConnectorSnapshotEvidence:
    connector_name: str
    timestamp: float
    hardware_snapshot: Any
    quality: str
    errors: tuple[str, ...] = ()
