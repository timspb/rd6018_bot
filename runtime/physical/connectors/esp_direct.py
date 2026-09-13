from __future__ import annotations

from typing import Any

from runtime.config import ConfigBundle
from runtime.output.bridge import HardwareCapability, HardwareSnapshot
from runtime.physical.transports import ESPHomeTransport

from .base import IndependentPhysicalConnector


class ESPDirectConnector(IndependentPhysicalConnector):
    name = "esp_direct"

    def __init__(self, config: ConfigBundle):
        self.transport = ESPHomeTransport(config.transports["esp128"], config.rd)

    async def discover(self) -> Any:
        return await self.transport.discover()

    async def health_check(self) -> dict[str, Any]:
        return await self.transport.health_check()

    async def get_snapshot(self) -> HardwareSnapshot:
        return await self.transport.get_snapshot()

    async def read_snapshot(self) -> HardwareSnapshot:
        return await self.transport.get_snapshot()

    async def disable_output(self) -> None:
        await self.transport.disable_output()

    async def get_capabilities(self) -> HardwareCapability:
        return await self.transport.get_capabilities()

    async def close(self) -> None:
        await self.transport.close()
