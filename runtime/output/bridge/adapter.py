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
