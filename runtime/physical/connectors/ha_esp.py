from __future__ import annotations

from typing import Any

from runtime.config import ConfigBundle
from runtime.output.bridge import HardwareCapability, HardwareSnapshot
from runtime.physical.transports import HA102Transport

from .base import IndependentPhysicalConnector


class HAESPConnector(IndependentPhysicalConnector):
    name = "ha_esp"

    def __init__(self, config: ConfigBundle):
        self.transport = HA102Transport(config.transports["ha102"], config.rd)

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

    async def _set_number(self, key: str, value: float) -> None:
        entity_id = self.transport.config.entities.get(key)
        if not entity_id:
            raise RuntimeError(f"HA control entity is not configured: {key}")
        if self.transport._session is None or self.transport._session.closed:
            await self.transport.health_check()
        scheme = "https" if self.transport.config.connection.tls else "http"
        url = f"{scheme}://{self.transport.config.connection.host}:{self.transport.config.connection.port}/api/services/number/set_value"
        async with self.transport._session.post(url, json={"entity_id": entity_id, "value": value}, ssl=False) as response:
            if response.status not in {200, 201}:
                raise RuntimeError(f"HA number write failed: HTTP {response.status}")

    async def set_voltage(self, value: float) -> None:
        await self._set_number("control_voltage", value)

    async def set_current(self, value: float) -> None:
        await self._set_number("control_current", value)

    async def set_ovp(self, value: float) -> None:
        await self._set_number("control_ovp", value)

    async def set_ocp(self, value: float) -> None:
        await self._set_number("control_ocp", value)

    async def enable_output(self) -> None:
        entity_id = self.transport.config.entities.get("control_output")
        if not entity_id:
            raise RuntimeError("HA output control entity is not configured")
        if self.transport._session is None or self.transport._session.closed:
            await self.transport.health_check()
        scheme = "https" if self.transport.config.connection.tls else "http"
        url = f"{scheme}://{self.transport.config.connection.host}:{self.transport.config.connection.port}/api/services/switch/turn_on"
        async with self.transport._session.post(url, json={"entity_id": entity_id}, ssl=False) as response:
            if response.status not in {200, 201}:
                raise RuntimeError(f"HA enable failed: HTTP {response.status}")

    async def get_capabilities(self) -> HardwareCapability:
        return await self.transport.get_capabilities()

    async def close(self) -> None:
        await self.transport.close()
