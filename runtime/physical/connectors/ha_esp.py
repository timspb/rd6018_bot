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
        raise RuntimeError("HAESPConnector is read-only; use the V2 physical owner")

    async def _set_number(self, key: str, value: float) -> None:
        raise RuntimeError("HAESPConnector is read-only; use the V2 physical owner")

    async def set_voltage(self, value: float) -> None:
        await self._set_number("control_voltage", value)

    async def set_current(self, value: float) -> None:
        await self._set_number("control_current", value)

    async def set_ovp(self, value: float) -> None:
        await self._set_number("control_ovp", value)

    async def set_ocp(self, value: float) -> None:
        await self._set_number("control_ocp", value)

    async def enable_output(self) -> None:
        raise RuntimeError("HAESPConnector is read-only; use the V2 physical owner")

    async def get_capabilities(self) -> HardwareCapability:
        return await self.transport.get_capabilities()

    async def close(self) -> None:
        await self.transport.close()
