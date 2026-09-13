from __future__ import annotations

import os
import time
from typing import Any

import aiohttp

from runtime.config.models import PhysicalTransportConfig, RDConfig
from runtime.output.bridge import HardwareCapability, HardwareSnapshot

from .base import ReadOnlyTransport


class HA102Transport(ReadOnlyTransport):
    def __init__(self, config: PhysicalTransportConfig, rd: RDConfig):
        self.config, self.rd = config, rd
        self._session: aiohttp.ClientSession | None = None

    async def _get(self, entity_id: str) -> dict[str, Any]:
        if self._session is None or self._session.closed:
            token = os.getenv(self.config.connection.token_env or "", "")
            if not token:
                raise RuntimeError("HA transport token environment variable is not set")
            self._session = aiohttp.ClientSession(headers={"Authorization": f"Bearer {token}"})
        scheme = "https" if self.config.connection.tls else "http"
        url = f"{scheme}://{self.config.connection.host}:{self.config.connection.port}/api/states/{entity_id}"
        async with self._session.get(url, ssl=False) as response:
            if response.status != 200:
                raise RuntimeError(f"HA read failed: HTTP {response.status}")
            return await response.json()

    async def discover(self):
        return tuple(self.config.entities.values())

    async def get_snapshot(self) -> HardwareSnapshot:
        values = {key: await self._get(entity) for key, entity in self.config.entities.items()}
        def number(key):
            value = values.get(key, {}).get("state")
            try: return float(value)
            except (TypeError, ValueError): return None
        output = values.get("output_state", {}).get("state")
        state = None if output is None else str(output) not in {"0", "off", "false", "unknown", "unavailable"}
        return HardwareSnapshot(time.time(), "connected", output_state=state, measured_voltage=number("voltage"), measured_current=number("current"), configured_voltage=number("configured_voltage"), configured_current=number("configured_current"), ovp=number("ovp"), ocp=number("ocp"))

    async def get_capabilities(self):
        return HardwareCapability(False, False, 0.01, self.rd.max_voltage_v, 0.01, 0.01, self.rd.max_current_a, 0.01, False, False, False, True, True, True)

    async def health_check(self):
        await self._get(next(iter(self.config.entities.values())))
        return {"connected": True, "transport": self.config.name, "read_only": True}

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
