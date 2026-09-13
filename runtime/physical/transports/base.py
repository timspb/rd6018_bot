from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from runtime.output.bridge import HardwareCapability, HardwareSnapshot, PhysicalBridgeAdapter


class ReadOnlyTransport(PhysicalBridgeAdapter, ABC):
    @abstractmethod
    async def discover(self) -> Any: ...

    @abstractmethod
    async def get_snapshot(self) -> HardwareSnapshot: ...

    @abstractmethod
    async def get_capabilities(self) -> HardwareCapability: ...

    @abstractmethod
    async def health_check(self) -> dict[str, Any]: ...

    async def discover_capabilities(self) -> HardwareCapability:
        return await self.get_capabilities()

    async def read_snapshot(self) -> HardwareSnapshot:
        return await self.get_snapshot()

    async def get_health(self) -> dict[str, Any]:
        return await self.health_check()
