"""Read-only physical bridge adapter interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Mapping

from .capabilities import HardwareCapability
from .snapshot import HardwareSnapshot


class PhysicalBridgeAdapter(ABC):
    @abstractmethod
    def discover_capabilities(self) -> HardwareCapability:
        raise NotImplementedError

    @abstractmethod
    def read_snapshot(self) -> HardwareSnapshot:
        raise NotImplementedError

    @abstractmethod
    def get_health(self) -> Mapping[str, object]:
        raise NotImplementedError


class LegacyHardwareAdapter:
    """Map an already-collected V2 hardware report without transport access."""

    @staticmethod
    def capability_from_mapping(data: Mapping[str, object]) -> HardwareCapability:
        return HardwareCapability(**{field: data[field] for field in HardwareCapability.__dataclass_fields__})

    @staticmethod
    def snapshot_from_mapping(data: Mapping[str, object]) -> HardwareSnapshot:
        return HardwareSnapshot(**{field: data.get(field) for field in HardwareSnapshot.__dataclass_fields__})
