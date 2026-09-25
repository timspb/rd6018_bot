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

    async def get_all_live(self) -> dict[str, Any]:
        return await self.transport.get_live_values()

    async def disable_output(self) -> None:
        await self.transport.disable_output()

    async def _set_number(self, key: str, value: float) -> None:
        wanted = self.transport.config.entities.get(key)
        entity = next((item for item in self.transport.entities if item.object_id == wanted), None)
        if entity is None or self.transport.client is None:
            raise RuntimeError(f"ESPHome numeric control entity is not available: {key}")
        self.transport.client.number_command(int(entity.key), float(value), int(entity.device_id))

    async def set_voltage(self, value: float) -> None:
        await self._set_number("control_voltage", value)

    async def set_current(self, value: float) -> None:
        await self._set_number("control_current", value)

    async def set_ovp(self, value: float) -> None:
        await self._set_number("control_ovp", value)

    async def set_ocp(self, value: float) -> None:
        await self._set_number("control_ocp", value)

    async def enable_output(self) -> None:
        wanted = self.transport.config.entities.get("control_output")
        entity = next((item for item in self.transport.entities if item.object_id == wanted), None)
        if entity is None or self.transport.client is None:
            raise RuntimeError("ESPHome output control entity is not available")
        self.transport.client.switch_command(int(entity.key), True, int(entity.device_id))

    async def get_capabilities(self) -> HardwareCapability:
        return await self.transport.get_capabilities()

    async def close(self) -> None:
        await self.transport.close()
